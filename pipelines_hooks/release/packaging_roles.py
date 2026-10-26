"""Validate an explicit package-role to extra closure contract.

The wheel-readiness action already proves dependency closure for each selected
runtime extra.  This small value layer gives callers a typed, digest-bound
role inventory to place beside that proof.  It deliberately has no default
roles or extras: a consumer must declare the role mapping, and the wheel
metadata remains authoritative for which extras exist.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from packaging.utils import canonicalize_name

from pipelines_hooks.core.errors import CannotRun

SCHEMA_VERSION = 1
_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, order=True)
class RoleBinding:
    """One declared role and the wheel extra that supplies it.

    ``extra=None`` denotes the base role.  The role name is consumer-owned;
    this module never invents or silently aliases product roles.
    """

    role: str
    extra: str | None


@dataclass(frozen=True)
class RoleContract:
    """Versioned role inventory read from a caller-supplied JSON object."""

    version: int
    bindings: tuple[RoleBinding, ...]


@dataclass(frozen=True)
class RoleProof:
    """One role's independent closure result."""

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


def parse_proof(raw: Mapping[str, Any]) -> tuple[RoleProof, ...]:
    """Parse one independent closure result per declared role."""
    if not isinstance(raw, Mapping) or set(raw) != {"roles"}:
        raise _invalid("evidence requires exactly roles")
    items = raw["roles"]
    if not isinstance(items, list):
        raise _invalid("evidence roles must be a list")
    proofs: list[RoleProof] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping) or set(item) != {"role", "extra", "status", "evidence_digest"}:
            raise _invalid(f"evidence roles[{index}] has an unsupported shape")
        role = _name(item["role"], what=f"evidence roles[{index}].role")
        if role in seen:
            raise _invalid(f"duplicate evidence role {role!r}")
        seen.add(role)
        extra = _extra(item["extra"])
        status = item["status"]
        if status not in {"pass", "fail"}:
            raise _invalid(f"evidence roles[{index}].status must be pass or fail")
        digest = item["evidence_digest"]
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest) or set(digest) == {"0"}:
            raise _invalid(f"evidence roles[{index}].evidence_digest must be sha256")
        proofs.append(RoleProof(role=role, extra=extra, status=status, evidence_digest=digest))
    return tuple(sorted(proofs, key=lambda item: item.role))


def verify(contract: RoleContract, metadata: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Return deterministic role evidence or raise on an unchecked surface."""
    bindings = validate_metadata(contract, metadata)
    proofs = parse_proof(evidence)
    expected = {binding.role: binding for binding in bindings}
    observed = {proof.role: proof for proof in proofs}
    if set(observed) != set(expected):
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        raise _invalid(f"evidence role inventory mismatch (missing={missing}, extra={extra})")
    for role, binding in expected.items():
        proof = observed[role]
        if proof.extra != binding.extra:
            raise _invalid(f"evidence extra mismatch for role {role!r}")
    payload = {
        "schema": SCHEMA_VERSION,
        "roles": [asdict(binding) for binding in bindings],
        "evidence": [asdict(proof) for proof in proofs],
        "status": "pass" if all(proof.status == "pass" for proof in proofs) else "fail",
    }
    return payload


def _read(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _invalid(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise _invalid(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    """Validate a role contract against wheel metadata and closure evidence."""
    parser = argparse.ArgumentParser(prog="packaging-roles")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(parse_contract(_read(args.contract)), _read(args.metadata), _read(args.evidence))
    except CannotRun as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
