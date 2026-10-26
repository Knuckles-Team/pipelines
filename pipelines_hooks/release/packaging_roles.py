"""Validate package-role closure against an existing wheel-readiness receipt.

The wheel-readiness action owns artifact metadata parsing and runtime closure
verification. This gate binds its receipt to one exact wheel digest and
projects the verified profile results into the declared role inventory. It
does not accept caller-authored metadata or resolver results as proof.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from packaging.utils import canonicalize_name

from pipelines_hooks.core.errors import CannotRun

SCHEMA_VERSION = 1
_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, order=True)
class RoleBinding:
    """One declared role and the wheel extra that supplies it."""

    role: str
    extra: str | None


@dataclass(frozen=True)
class RoleContract:
    """Versioned role inventory read from a caller-supplied JSON object."""

    version: int
    bindings: tuple[RoleBinding, ...]


@dataclass(frozen=True)
class RoleProof:
    """One role's independently verified readiness result."""

    role: str
    extra: str | None
    status: str
    evidence_digest: str


def _invalid(message: str) -> CannotRun:
    return CannotRun(f"packaging-role-contract: {message}")


def _name(value: object, *, what: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise _invalid(f"{what} must be a nonempty package-style name")
    return value


def _extra(value: object) -> str | None:
    if value is None:
        return None
    raw = _name(value, what="extra")
    normalized = canonicalize_name(raw)
    if normalized == "base":
        raise _invalid("base is represented by null extra")
    return normalized


def parse_contract(raw: Mapping[str, Any]) -> RoleContract:
    """Parse a strict role contract without supplying policy defaults."""
    if not isinstance(raw, Mapping) or set(raw) != {"version", "roles"}:
        raise _invalid("contract requires exactly version and roles")
    if raw["version"] != SCHEMA_VERSION:
        raise _invalid(f"unsupported schema version {raw['version']!r}")
    roles = raw["roles"]
    if not isinstance(roles, list) or not roles:
        raise _invalid("roles must be a nonempty list")
    bindings: list[RoleBinding] = []
    seen_roles: set[str] = set()
    for index, item in enumerate(roles):
        if not isinstance(item, Mapping) or set(item) != {"role", "extra"}:
            raise _invalid(f"roles[{index}] requires exactly role and extra")
        role = _name(item["role"], what=f"roles[{index}].role")
        if role in seen_roles:
            raise _invalid(f"duplicate role {role!r}")
        seen_roles.add(role)
        bindings.append(RoleBinding(role=role, extra=_extra(item["extra"])))
    base = [binding for binding in bindings if binding.extra is None]
    if len(base) != 1 or base[0].role != "base":
        raise _invalid("exactly one role named base must use a null extra")
    extras = [binding.extra for binding in bindings if binding.extra is not None]
    if len(set(extras)) != len(extras):
        raise _invalid("each role must name a distinct extra")
    return RoleContract(version=SCHEMA_VERSION, bindings=tuple(sorted(bindings)))


def validate_metadata(contract: RoleContract, metadata: Mapping[str, Any]) -> tuple[RoleBinding, ...]:
    """Ensure every declared role extra exists in authoritative wheel metadata."""
    if not isinstance(metadata, Mapping) or set(metadata) != {"provides_extra"}:
        raise _invalid("metadata requires exactly provides_extra")
    provided = metadata["provides_extra"]
    if not isinstance(provided, list) or not all(isinstance(item, str) for item in provided):
        raise _invalid("provides_extra must be a list of strings")
    normalized = []
    for item in provided:
        extra = _extra(item)
        if extra is None:
            raise _invalid("metadata provides_extra cannot contain the reserved base extra")
        normalized.append(extra)
    if len(set(normalized)) != len(normalized):
        raise _invalid("metadata provides duplicate extras")
    available = set(normalized)
    for binding in contract.bindings:
        if binding.extra is not None and binding.extra not in available:
            raise _invalid(f"role {binding.role!r} names undeclared extra {binding.extra!r}")
    return contract.bindings


def _readiness_checker(path: Path) -> ModuleType:
    if not path.is_file() or path.is_symlink():
        raise _invalid(f"wheel-readiness checker is not a regular file: {path}")
    spec = importlib.util.spec_from_file_location("pipelines_wheel_readiness", path)
    if spec is None or spec.loader is None:
        raise _invalid(f"cannot load wheel-readiness checker: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError, SyntaxError) as exc:
        raise _invalid(f"cannot load wheel-readiness checker {path}: {exc}") from exc
    return module


def _receipt_item(
    receipt: Mapping[str, Any], wheel: Path
) -> tuple[Mapping[str, Any], Mapping[str, Any], tuple[str, ...]]:
    if receipt.get("schema") != SCHEMA_VERSION or receipt.get("scope") != "all-runtime-dependencies":
        raise _invalid("readiness receipt has unsupported schema or scope")
    context = receipt.get("context")
    if not isinstance(context, Mapping):
        raise _invalid("readiness receipt has no context")
    source_builds = receipt.get("source_builds")
    if not isinstance(source_builds, list) or not all(isinstance(item, str) for item in source_builds):
        raise _invalid("readiness receipt has no source-build inventory")
    wheels = receipt.get("wheels")
    if not isinstance(wheels, list):
        raise _invalid("readiness receipt has no wheel inventory")
    matches = [item for item in wheels if isinstance(item, Mapping) and item.get("file") == wheel.name]
    if len(matches) != 1:
        raise _invalid(f"readiness receipt must contain exactly one wheel item for {wheel.name}")
    item = matches[0]
    return item, context, tuple(source_builds)


def _profiles(contract: RoleContract) -> list[str]:
    values = ["base", *(binding.extra for binding in contract.bindings if binding.extra is not None)]
    return sorted(values)


def _evidence_digest(entry: Mapping[str, Any]) -> str:
    payload = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify(
    contract: RoleContract,
    wheel: Path,
    expected_digest: str,
    receipt: Mapping[str, Any],
    readiness_path: Path,
    runtime_profiles: str | None = None,
) -> dict[str, Any]:
    """Verify one exact wheel through the existing readiness implementation."""
    if not _SHA256.fullmatch(expected_digest) or set(expected_digest) == {"0"}:
        raise _invalid("wheel-sha256 must be a nonzero lowercase SHA-256 digest")
    if not wheel.is_file() or wheel.is_symlink():
        raise _invalid(f"wheel is not a regular file: {wheel}")
    readiness = _readiness_checker(readiness_path)
    try:
        actual_digest = readiness.digest(wheel)
    except (OSError, TypeError, ValueError) as exc:
        raise _invalid(f"cannot hash wheel: {exc}") from exc
    if actual_digest != expected_digest:
        raise _invalid("wheel bytes do not match wheel-sha256")
    item, context, source_builds = _receipt_item(receipt, wheel)
    try:
        if receipt.get("index") != readiness.PUBLIC_INDEX:
            raise _invalid("readiness receipt index is not the approved public index")
        if receipt.get("interpreter") != context.get("interpreter"):
            raise _invalid("readiness receipt interpreter is not bound to its context")
        if readiness.observed_context() != context:
            raise _invalid("readiness receipt context does not match this verifier")
        if tuple(readiness.source_build_allowance()) != source_builds:
            raise _invalid("readiness source-build allowance changed")
    except CannotRun:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        raise _invalid(f"readiness receipt context cannot be verified: {exc}") from exc
    if item.get("sha256") != actual_digest:
        raise _invalid("readiness receipt wheel digest does not match artifact bytes")
    try:
        actual_metadata = readiness.metadata(wheel, context)
    except (KeyError, OSError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        raise _invalid(f"wheel metadata cannot be verified: {exc}") from exc
    if item.get("metadata") != actual_metadata:
        raise _invalid("readiness receipt metadata does not match artifact bytes")
    validate_metadata(contract, {"provides_extra": actual_metadata.get("provides_extra", [])})
    expected_profiles = _profiles(contract)
    profiles = item.get("profiles")
    if not isinstance(profiles, list) or profiles != expected_profiles:
        raise _invalid(f"role/profile inventory mismatch (expected={expected_profiles}, observed={profiles})")
    if runtime_profiles is not None:
        try:
            actual_profiles = readiness.profiles(runtime_profiles, actual_metadata["provides_extra"])
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise _invalid(f"runtime profiles cannot be verified: {exc}") from exc
        if actual_profiles != expected_profiles:
            raise _invalid(
                f"role/profile inventory does not match runtime profiles "
                f"(expected={actual_profiles}, observed={expected_profiles})"
            )
    try:
        readiness.verify_item(wheel, item, json.dumps(expected_profiles), context, source_builds)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise _invalid(f"readiness closure proof failed: {exc}") from exc
    entries = item.get("evidence")
    if not isinstance(entries, list):
        raise _invalid("readiness receipt has no profile evidence")
    by_profile = {"base" if binding.extra is None else binding.extra: binding for binding in contract.bindings}
    proofs: list[RoleProof] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("profile"), str):
            raise _invalid("readiness profile evidence has unsupported shape")
        profile = entry["profile"]
        if profile in seen or profile not in by_profile:
            raise _invalid(f"readiness profile evidence does not match role inventory: {profile!r}")
        seen.add(profile)
        binding = by_profile[profile]
        proofs.append(RoleProof(binding.role, binding.extra, "pass", _evidence_digest(entry)))
    if seen != set(by_profile):
        raise _invalid("readiness profile evidence is incomplete")
    proofs.sort(key=lambda item: item.role)
    return {
        "schema": SCHEMA_VERSION,
        "artifact": {"file": wheel.name, "sha256": actual_digest, "metadata": actual_metadata},
        "roles": [asdict(binding) for binding in contract.bindings],
        "evidence": [asdict(proof) for proof in proofs],
        "status": "pass",
    }


def _read(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _invalid(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise _invalid(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    """Validate one exact wheel through the published readiness receipt."""
    parser = argparse.ArgumentParser(prog="packaging-roles")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--wheel-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--readiness-checker", type=Path, default=Path(".github/actions/wheel-readiness/readiness.py"))
    parser.add_argument("--runtime-profiles")
    args = parser.parse_args(argv)
    try:
        result = verify(
            parse_contract(_read(args.contract)),
            args.wheel,
            args.wheel_sha256,
            _read(args.receipt),
            args.readiness_checker,
            args.runtime_profiles,
        )
    except CannotRun as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
