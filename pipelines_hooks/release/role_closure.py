"""Prove each supported role installs from its own frozen closure.

The package owner publishes one role export: the supported roles, and for each
the root distribution, extras, entry modules and the platform-qualified
transitive closure. This gate binds that export by repository, source revision
and digest, requires its role set to equal the packaging-role contract, builds
an isolated environment per role from only the closure wheels, and measures the
imports. It never installs dependencies to repair a candidate, and a missing
export is a refusal, not a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.release.packaging_roles import parse_contract

SCHEMA_VERSION = 1
MANDATORY_ROOT = "medulla"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


@dataclass(frozen=True)
class ClosureDist:
    """One distribution of a role's closure for one platform."""

    name: str
    version: str
    platform: str
    modules: tuple[str, ...]


@dataclass(frozen=True)
class RoleSpec:
    """One supported role as the package owner exports it."""

    role: str
    root: str
    extras: tuple[str, ...]
    entry_modules: tuple[str, ...]
    closure: tuple[ClosureDist, ...]


@dataclass(frozen=True)
class RoleExtraManifest:
    """The owner export bound by repository, source revision and digest."""

    repository: str
    revision: str
    digest: str
    lock_sha256: str
    targets: tuple[str, ...]
    roles: tuple[RoleSpec, ...]


#: ``(role, wheel_dir, closure, imports) -> (installed distributions, import outcomes)``.
Prober = Callable[
    [RoleSpec, Path, Sequence[ClosureDist], Sequence[str]],
    tuple[list[str], dict[str, bool]],
]


def _refuse(reason: str, detail: str) -> CannotRun:
    return CannotRun(f"role-closure: {reason}: {detail}")


def canonical_digest(payload: Any) -> str:
    """Digest of the canonical JSON form; the export's ``digest`` covers its roles and targets."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _strings(value: object, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise _refuse("export-invalid", f"{what} must be a list of nonempty strings")
    return tuple(value)


def _dist(raw: object, targets: tuple[str, ...]) -> ClosureDist:
    if not isinstance(raw, Mapping) or set(raw) != {"name", "version", "platform", "modules"}:
        raise _refuse("export-invalid", "closure entries need name, version, platform and modules")
    name, version, platform = raw["name"], raw["version"], raw["platform"]
    if not (isinstance(name, str) and name and isinstance(version, str) and version):
        raise _refuse("unresolved-version", f"closure entry {name!r} has no resolved version")
    if platform not in targets:
        raise _refuse("export-invalid", f"{name} names undeclared platform {platform!r}")
    modules = _strings(raw["modules"], f"{name}.modules")
    if not all(_MODULE.fullmatch(module) for module in modules):
        raise _refuse("export-invalid", f"{name} lists a malformed module name")
    return ClosureDist(name, version, platform, modules)


def _role(raw: object, targets: tuple[str, ...]) -> RoleSpec:
    keys = {"role", "root", "extras", "entry_modules", "closure"}
    if not isinstance(raw, Mapping) or set(raw) != keys:
        raise _refuse("export-invalid", f"a role needs exactly {sorted(keys)}")
    closure = raw["closure"]
    if not isinstance(closure, list):
        raise _refuse("export-invalid", "closure must be a list")
    spec = RoleSpec(
        role=str(raw["role"]),
        root=str(raw["root"]),
        extras=_strings(raw["extras"], "extras"),
        entry_modules=_strings(raw["entry_modules"], "entry_modules"),
        closure=tuple(_dist(item, targets) for item in closure),
    )
    covered = {item.platform for item in spec.closure}
    if covered != set(targets):
        raise _refuse("incomplete-targets", f"role {spec.role} covers {sorted(covered)}, expected {sorted(targets)}")
    for target in targets:
        if MANDATORY_ROOT not in {d.name for d in spec.closure if d.platform == target}:
            raise _refuse("missing-mandatory", f"role {spec.role} closure on {target} has no {MANDATORY_ROOT}")
    return spec


def parse_export(raw: Mapping[str, Any]) -> RoleExtraManifest:
    """Parse and digest-check one owner export."""
    keys = {"schema", "repository", "revision", "digest", "lock_sha256", "targets", "roles"}
    if not isinstance(raw, Mapping) or set(raw) != keys or raw["schema"] != SCHEMA_VERSION:
        raise _refuse("export-invalid", f"the export needs exactly {sorted(keys)} at schema {SCHEMA_VERSION}")
    if not all(isinstance(raw[k], str) and raw[k] for k in ("repository", "revision")):
        raise _refuse("export-invalid", "repository and revision must be nonempty strings")
    if not (_SHA256.fullmatch(str(raw["digest"])) and _SHA256.fullmatch(str(raw["lock_sha256"]))):
        raise _refuse("export-invalid", "digest and lock_sha256 must be SHA-256 digests")
    body = {"targets": raw["targets"], "roles": raw["roles"]}
    if canonical_digest(body) != raw["digest"]:
        raise _refuse("export-digest", "the export bytes do not match its digest")
    targets = _strings(raw["targets"], "targets")
    roles = raw["roles"]
    if not isinstance(roles, list) or not roles:
        raise _refuse("export-invalid", "roles must be a nonempty list")
    return RoleExtraManifest(
        raw["repository"],
        raw["revision"],
        raw["digest"],
        raw["lock_sha256"],
        targets,
        tuple(_role(item, targets) for item in roles),
    )


def check_role_set(manifest: RoleExtraManifest, contract_roles: Sequence[str]) -> None:
    """The exported supported-role set must equal the contract's role set."""
    exported = sorted(role.role for role in manifest.roles)
    if exported != sorted(contract_roles):
        raise _refuse("role-set", f"export has {exported}, the contract declares {sorted(contract_roles)}")


def import_plan(manifest: RoleExtraManifest, role: RoleSpec, target: str) -> tuple[list[str], list[str], bool]:
    """Required imports, forbidden imports and whether a real negative case exists.

    Forbidden probes cover only modules outside this role's resolved closure on the target.
    """
    mine = {m for d in role.closure if d.platform == target for m in d.modules}
    required = sorted({*role.entry_modules, *mine})
    others = {
        m
        for other in manifest.roles
        if other.role != role.role
        for d in other.closure
        if d.platform == target
        for m in d.modules
    }
    forbidden = sorted(others - mine)
    return required, forbidden, bool(forbidden)


def venv_prober(
    role: RoleSpec, wheel_dir: Path, closure: Sequence[ClosureDist], imports: Sequence[str]
) -> tuple[list[str], dict[str, bool]]:
    """Install only the closure wheels offline into a fresh environment and import each module."""
    work = Path(tempfile.mkdtemp(prefix="role-closure-"))
    try:
        env = work / "env"
        subprocess.run([sys.executable, "-m", "venv", str(env)], check=True, capture_output=True)
        python = str(env / "bin" / "python")
        pins = [f"{d.name}=={d.version}" for d in closure]
        subprocess.run(
            [python, "-m", "pip", "install", "--no-deps", "--no-index", "--find-links", str(wheel_dir), *pins],
            check=True,
            capture_output=True,
        )
        listed = subprocess.run(
            [python, "-m", "pip", "list", "--format=json"], check=True, capture_output=True, text=True
        )
        installed = sorted(f"{item['name']}=={item['version']}" for item in json.loads(listed.stdout))
        outcomes = {
            module: subprocess.run([python, "-c", f"import {module}"], capture_output=True).returncode == 0
            for module in imports
        }
        return installed, outcomes
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _refuse("install-failed", f"role {role.role}: {type(exc).__name__}") from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _wheel_digests(wheel_dir: Path) -> dict[str, str]:
    wheels = sorted(wheel_dir.glob("*.whl")) if wheel_dir.is_dir() else []
    if not wheels:
        raise _refuse("artifact-missing", "no built wheels found in the artifact directory")
    return {w.name: hashlib.sha256(w.read_bytes()).hexdigest() for w in wheels}


def evaluate(manifest: RoleExtraManifest, wheel_dir: Path, lock: Path, prober: Prober) -> tuple[int, dict[str, Any]]:
    """Measure every role on every target; return the exit status and the evidence."""
    if not lock.is_file() or hashlib.sha256(lock.read_bytes()).hexdigest() != manifest.lock_sha256:
        raise _refuse("stale-lock", "the lock does not match the export's lock digest")
    artifacts = _wheel_digests(wheel_dir)
    findings: list[str] = []
    limitations: list[str] = []
    evidence: list[dict[str, Any]] = []
    for role in sorted(manifest.roles, key=lambda r: r.role):
        for target in manifest.targets:
            closure = [d for d in role.closure if d.platform == target]
            required, forbidden, has_negative = import_plan(manifest, role, target)
            installed, outcomes = prober(role, wheel_dir, closure, [*required, *forbidden])
            findings += [f"{role.role}/{target}: required import {m} failed" for m in required if not outcomes.get(m)]
            findings += [f"{role.role}/{target}: excluded import {m} succeeded" for m in forbidden if outcomes.get(m)]
            if not has_negative:
                limitations.append(
                    f"{role.role}/{target}: no excluded import exists; the negative obligation is not proved"
                )
            evidence.append(
                {
                    "role": role.role,
                    "target": target,
                    "extras": list(role.extras),
                    "mandatory": [d.name for d in closure if d.name == MANDATORY_ROOT],
                    "installed": installed,
                    "imports": {m: bool(outcomes.get(m)) for m in [*required, *forbidden]},
                }
            )
    report = {
        "schema": SCHEMA_VERSION,
        "repository": manifest.repository,
        "revision": manifest.revision,
        "export_digest": manifest.digest,
        "lock_sha256": manifest.lock_sha256,
        "artifacts": artifacts,
        "roles": evidence,
        "findings": sorted(findings),
        "limitations": sorted(limitations),
        "status": "fail" if findings else "pass",
    }
    return (1 if findings else 0), report


def _read(path: Path, reason: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _refuse(reason, f"cannot read {path.name}") from exc
    if not isinstance(value, Mapping):
        raise _refuse(reason, f"{path.name} must hold a JSON object")
    return value


def main(argv: list[str] | None = None, prober: Prober = venv_prober) -> int:
    """Check one built package against the owner's role export."""
    parser = argparse.ArgumentParser(prog="role-closure")
    parser.add_argument("--export", type=Path, required=True, help="the package owner's role export")
    parser.add_argument("--contract", type=Path, required=True, help="the packaging-roles contract")
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.export.is_file():
            raise _refuse("owner-export-missing", "the package owner has not published a role export")
        manifest = parse_export(_read(args.export, "export-invalid"))
        check_role_set(manifest, [b.role for b in parse_contract(_read(args.contract, "contract-invalid")).bindings])
        status, report = evaluate(manifest, args.wheel_dir, args.lock, prober)
    except CannotRun as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
