"""Validate tracked package paths against the source portability policy.

The package build must receive the same source tree on Linux, macOS and
Windows.  This gate therefore checks the *tracked Git names*, rather than the
names that happen to be present in a contributor's worktree.  The policy is
deliberately about relative source paths under the package roots declared in
``[tool.pipelines_hooks].packages``; it makes no claim about an arbitrary
checkout prefix or an installation directory.

Policy version 1 measures repository-relative paths after NFC normalization:

* the complete path is at most 240 UTF-16 code units;
* every component is at most 255 UTF-8 bytes;
* absolute paths, traversal, control characters, Windows-invalid characters,
  trailing spaces or periods and Windows device names are forbidden; and
* two names that collide after NFC normalization and case folding are
  forbidden.

The module exposes a small pure scanner (``inspect_paths``) so consumers that
already inventory source paths can use one implementation.  ``scan`` is the
repository adapter used by the published gate and reports the source
snapshot, package roots, original spellings and normalized comparison keys.
It never renames, rewrites or reads source bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from pipelines_hooks.core.config import load_config
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, repo_root
from pipelines_hooks.core.tracked import tracked_paths

POLICY_VERSION = 1
MAX_PATH_UTF16 = 240
MAX_COMPONENT_UTF8 = 255
SUPPORTED_PLATFORMS = ("linux", "macos", "windows")

_WINDOWS_INVALID = frozenset('<>:"|?*\\')
_WINDOWS_RESERVED = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
)
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class PathPortabilityPolicy:
    """Versioned limits and roots for one source-path census."""

    version: int = POLICY_VERSION
    max_path_utf16: int = MAX_PATH_UTF16
    max_component_utf8: int = MAX_COMPONENT_UTF8
    package_roots: tuple[str, ...] = ()
    supported_platforms: tuple[str, ...] = SUPPORTED_PLATFORMS

    def validate(self) -> None:
        """Reject an unsupported or weakening policy before scanning paths."""
        if self.version != POLICY_VERSION:
            raise CannotRun(f"unsupported source-path portability policy version: {self.version!r}")
        if not isinstance(self.max_path_utf16, int) or self.max_path_utf16 <= 0:
            raise CannotRun("source-path portability max_path_utf16 must be a positive integer")
        if not isinstance(self.max_component_utf8, int) or self.max_component_utf8 <= 0:
            raise CannotRun("source-path portability max_component_utf8 must be a positive integer")
        if self.max_path_utf16 > MAX_PATH_UTF16:
            raise CannotRun(f"source-path portability max_path_utf16 cannot exceed policy limit {MAX_PATH_UTF16}")
        if self.max_component_utf8 > MAX_COMPONENT_UTF8:
            raise CannotRun(
                f"source-path portability max_component_utf8 cannot exceed policy limit {MAX_COMPONENT_UTF8}"
            )
        if not self.package_roots or any(not isinstance(root, str) or not root.strip() for root in self.package_roots):
            raise CannotRun("source-path portability requires declared package roots")
        if len(set(self.package_roots)) != len(self.package_roots):
            raise CannotRun("source-path portability package roots contain duplicates")
        if tuple(self.supported_platforms) != SUPPORTED_PLATFORMS:
            raise CannotRun("source-path portability supports exactly Linux, macOS and Windows")
        for root in self.package_roots:
            findings = _shape_findings(root)
            if findings:
                raise CannotRun(f"declared package root {root!r} is invalid: {', '.join(findings)}")


@dataclass(frozen=True)
class PathViolation:
    """One source path rule violation with enough location to repair it."""

    path: str
    rule: str
    detail: str
    platform: str
    component: str | None = None
    normalized_key: str | None = None
    measured: int | None = None
    limit: int | None = None
    related_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Serialize without dropping ``None`` fields useful to consumers."""
        return asdict(self)


@dataclass(frozen=True)
class PathReport:
    """Bounded, machine-readable result of a source path census."""

    policy_version: int
    source_snapshot: str
    package_roots: tuple[str, ...]
    supported_platforms: tuple[str, ...]
    inventory_digest: str
    checked_paths: tuple[dict[str, object], ...]
    violations: tuple[PathViolation, ...]

    @property
    def clean(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, object]:
        """Return the evidence contract consumed by hosted gates."""
        return {
            "schema": "source-path-portability/v1",
            "policy_version": self.policy_version,
            "source_snapshot": self.source_snapshot,
            "package_roots": list(self.package_roots),
            "supported_platforms": list(self.supported_platforms),
            "inventory_digest": self.inventory_digest,
            "checked_path_count": len(self.checked_paths),
            "checked_paths": list(self.checked_paths),
            "violations": [item.as_dict() for item in self.violations],
        }


def _utf16_units(value: str) -> int:
    """Count UTF-16 code units without assuming the host's native width."""
    return len(value.encode("utf-16-le")) // 2


def _normal_key(value: str) -> str:
    """The cross-platform comparison key required by policy version 1."""
    return unicodedata.normalize("NFC", value).casefold()


def _shape_findings(value: str) -> list[str]:
    """Return path-shape findings independent of package-root membership."""
    findings: list[str] = []
    if not value:
        return ["empty_path"]
    if value.startswith("/") or value.startswith("\\") or _WINDOWS_DRIVE.match(value):
        findings.append("absolute_path")
    if "\\" in value:
        findings.append("windows_separator")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        findings.append("traversal_or_empty_component")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        findings.append("control_character")
    if any(char in _WINDOWS_INVALID for char in value):
        findings.append("windows_invalid_character")
    return findings


def _reserved_stem(component: str) -> str:
    """Normalize a component enough for Windows device-name comparison."""
    return component.rstrip(" .").split(".", 1)[0].casefold()


def _inventory_digest(paths: Iterable[str]) -> str:
    """Hash original Git spellings in deterministic order for receipt binding."""
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode("utf-8", errors="strict"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _root_matches(path: str, root: str) -> bool:
    """Whether a repository-relative path is under a declared package root."""
    clean = root.rstrip("/")
    return path == clean or path.startswith(clean + "/")


def _record(path: str, policy: PathPortabilityPolicy) -> tuple[dict[str, object], list[PathViolation]]:
    """Measure and validate one original path spelling."""
    normalized = unicodedata.normalize("NFC", path)
    key = _normal_key(path)
    parts = path.split("/")
    findings = _shape_findings(path)
    violations: list[PathViolation] = []

    for finding in findings:
        violations.append(
            PathViolation(
                path=path,
                rule=finding,
                detail="path must be a relative, single-separator repository path",
                platform="windows/macOS/linux",
                normalized_key=key,
            )
        )

    path_units = _utf16_units(normalized)
    if path_units > policy.max_path_utf16:
        violations.append(
            PathViolation(
                path=path,
                rule="path_length",
                detail="normalized repository-relative path exceeds the UTF-16 limit",
                platform="windows/macOS/linux",
                normalized_key=key,
                measured=path_units,
                limit=policy.max_path_utf16,
            )
        )

    for component in parts:
        if not component:
            continue
        component_bytes = len(unicodedata.normalize("NFC", component).encode("utf-8"))
        if component_bytes > policy.max_component_utf8:
            violations.append(
                PathViolation(
                    path=path,
                    rule="component_length",
                    detail="normalized path component exceeds the UTF-8 byte limit",
                    platform="windows/macOS/linux",
                    component=component,
                    normalized_key=key,
                    measured=component_bytes,
                    limit=policy.max_component_utf8,
                )
            )
        if component.rstrip(" .") != component:
            violations.append(
                PathViolation(
                    path=path,
                    rule="trailing_space_or_period",
                    detail="Windows removes trailing spaces and periods from names",
                    platform="windows",
                    component=component,
                    normalized_key=key,
                )
            )
        if _reserved_stem(component) in _WINDOWS_RESERVED:
            violations.append(
                PathViolation(
                    path=path,
                    rule="reserved_name",
                    detail="component is a reserved Windows device name",
                    platform="windows",
                    component=component,
                    normalized_key=key,
                )
            )

    checked = {
        "path": path,
        "normalized_key": key,
        "utf16_path_units": path_units,
        "utf8_component_bytes": {
            component: len(unicodedata.normalize("NFC", component).encode("utf-8")) for component in parts if component
        },
    }
    return checked, violations


def inspect_paths(
    paths: Iterable[str],
    policy: PathPortabilityPolicy,
    *,
    source_snapshot: str = "unbound",
) -> PathReport:
    """Evaluate repository-relative source paths without touching their bytes."""
    policy.validate()
    originals = tuple(paths)
    if any(not isinstance(path, str) for path in originals):
        raise CannotRun("source-path portability inventory contains undecodable paths")
    try:
        for path in originals:
            path.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise CannotRun("source-path portability inventory contains undecodable paths") from exc
    checked: list[dict[str, object]] = []
    violations: list[PathViolation] = []
    by_key: dict[str, list[str]] = defaultdict(list)
    for path in originals:
        record, path_violations = _record(path, policy)
        checked.append(record)
        violations.extend(path_violations)
        by_key[str(record["normalized_key"])].append(path)

    for key, participants in sorted(by_key.items()):
        unique = tuple(sorted(set(participants)))
        if len(unique) < 2:
            continue
        for path in unique:
            violations.append(
                PathViolation(
                    path=path,
                    rule="casefold_nfc_collision",
                    detail="another tracked path has the same NFC case-folded comparison key",
                    platform="macos/windows",
                    normalized_key=key,
                    related_paths=unique,
                )
            )

    return PathReport(
        policy_version=policy.version,
        source_snapshot=source_snapshot,
        package_roots=policy.package_roots,
        supported_platforms=policy.supported_platforms,
        inventory_digest=_inventory_digest(originals),
        checked_paths=tuple(checked),
        violations=tuple(
            sorted(
                violations,
                key=lambda item: (item.path, item.rule, item.component or "", item.detail),
            )
        ),
    )


def load_policy(root: Path) -> PathPortabilityPolicy:
    """Load the package roots declared by the consumer's validated config."""
    config = load_config(root)
    return PathPortabilityPolicy(package_roots=config.required_packages())


def scan(root: Path, policy: PathPortabilityPolicy | None = None) -> PathReport:
    """Scan tracked paths under declared package roots in ``root``."""
    root = repo_root(Path(root))
    selected_policy = policy or load_policy(root)
    selected_policy.validate()
    all_paths = tracked_paths(root)
    selected = [
        path
        for path in all_paths
        if any(_root_matches(path, package_root.rstrip("/")) for package_root in selected_policy.package_roots)
    ]
    missing = [
        package_root
        for package_root in selected_policy.package_roots
        if not any(_root_matches(path, package_root.rstrip("/")) for path in all_paths)
    ]
    if missing:
        raise CannotRun("declared package root has no tracked source paths: " + ", ".join(sorted(missing)))
    snapshot = git_text(root, ("rev-parse", "HEAD")).strip()
    if not snapshot:
        raise CannotRun("source-path portability requires a committed source snapshot")
    return inspect_paths(selected, selected_policy, source_snapshot=snapshot)


def _print_report(report: PathReport, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        return
    if report.clean:
        print(
            "source path portability: clean "
            f"(policy v{report.policy_version}; {len(report.checked_paths)} tracked package paths; "
            f"roots={','.join(report.package_roots)})"
        )
        return
    print(
        "FAIL: source path portability violations "
        f"(policy v{report.policy_version}; {len(report.violations)} findings)."
    )
    for violation in report.violations:
        location = f" [{violation.component}]" if violation.component else ""
        related = f"; participants={','.join(violation.related_paths)}" if violation.related_paths else ""
        measured = f" ({violation.measured}>{violation.limit})" if violation.measured is not None else ""
        print(f"  {violation.path}{location}: {violation.rule}{measured} — {violation.detail}{related}")


def main(argv: list[str] | None = None) -> int:
    """Run the source-path portability gate for one repository."""
    parser = argparse.ArgumentParser(prog="source-path-portability", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", help="emit the evidence receipt as JSON")
    args = parser.parse_args(argv)
    report = scan(args.root)
    _print_report(report, as_json=args.json)
    return 0 if report.clean else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CannotRun as exc:
        print(f"source-path-portability: CANNOT RUN: {exc}", file=__import__("sys").stderr)
        raise SystemExit(2) from exc
