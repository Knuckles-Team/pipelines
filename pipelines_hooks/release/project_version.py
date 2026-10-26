"""Check project version locations declared by one bumpversion config.

The gate deliberately treats the bumpversion file as a small, versioned
manifest.  It reads only Git blobs (the index for a hook invocation and the
selected commit for a range/CI invocation); it never imports the project or
edits a file.  Role annotations live in the bumpversion section name so the
same configuration remains usable by bump2version::

    [bumpversion:file(metadata):pyproject.toml]
    search = version = "{current_version}"
    replace = version = "{new_version}"

A role suffix keeps the file section compatible with bump2version.  The
search template is the exact literal selector; its match count defaults to
one and may be declared as ``expected_count`` for adapters that support that
option.  Extraction stays independent from the expected version so a drift
yields a located mismatch instead of a misleading missing-selector refusal.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

from pipelines_hooks.core.comparison import comparison
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_text, git_text, repo_root, run_git

ROLES = ("metadata", "source", "documentation")
_ROLE_SET = frozenset(ROLES)
_SECTION_RE = re.compile(r"^bumpversion:file(?:\((?P<role>[^)]+)\))?:(?P<path>.+)$")
_PROJECT_SECTION_RE = re.compile(r"^project-version:(?P<role>[^:]+):(?P<path>.+)$")
_PLACEHOLDER_RE = re.compile(r"\{(?P<name>current_version|new_version)\}")
_ASSIGNMENT_RE = re.compile(
    r"(?m)^[ \t]*[A-Za-z_][A-Za-z0-9_]*"
    r"(?:[ \t]*:[^=\r\n]+)?[ \t]*=[ \t]*(?P<quote>['\"])"
)
_SAFE_VERSION_RE = re.compile(r"^[^\x00-\x1f\x7f\r\n]+$")
_MAX_CONFIG_BYTES = 512 * 1024
_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_CONFIG_CANDIDATES = (".config/bumpversion.cfg", ".bumpversion.cfg", "setup.cfg", "tox.ini")


@dataclass(frozen=True, order=True)
class VersionLocation:
    """One explicit project-version location from the canonical config."""

    path: str
    role: str
    selector: str
    search: str
    replace: str
    expected_count: int

    @property
    def repository_relative_path(self) -> str:
        """The path spelling used in evidence and receipts."""
        return self.path

    @property
    def extraction_selector(self) -> str:
        """The declared selector identity."""
        return self.selector

    @property
    def expected_matches(self) -> int:
        """Compatibility spelling for callers that call matches a count."""
        return self.expected_count


@dataclass(frozen=True)
class ProjectVersionInventory:
    """The typed inventory derived from one selected canonical config."""

    current_version: str
    locations: tuple[VersionLocation, ...]
    config_digest: str
    snapshot: str
    config_path: str = ".config/bumpversion.cfg"
    schema_version: int = 1

    @property
    def roles(self) -> frozenset[str]:
        """Roles represented by the inventory."""
        return frozenset(location.role for location in self.locations)


@dataclass(frozen=True)
class VersionCheck:
    """One observed version token and its exact source location."""

    location: VersionLocation
    expected: str
    actual: str
    line: int
    checked_count: int
    expected_count: int
    config_digest: str
    blob_digest: str
    snapshot: str

    @property
    def status(self) -> str:
        """The located verdict for this observation."""
        return "pass" if self.actual == self.expected else "version-mismatch"

    @property
    def path(self) -> str:
        return self.location.path

    @property
    def role(self) -> str:
        return self.location.role

    @property
    def selector(self) -> str:
        """The configured extraction selector identity."""
        return self.location.selector


def _safe_relative_path(value: str, *, what: str) -> str:
    """Validate and normalize a repository-relative POSIX path."""
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\x00" in value or "\\" in value:
        raise CannotRun(f"config-invalid: {what} must be a repository-relative path")
    if str(path) != value or path == PurePosixPath("."):
        raise CannotRun(f"config-invalid: {what} has an ambiguous path")
    return value


def _template_parts(template: str, placeholder: str) -> tuple[str, str]:
    """Return literal prefix/suffix for exactly one version placeholder."""
    if template.count(placeholder) != 1:
        raise CannotRun(f"config-invalid: template must contain exactly one {placeholder}")
    if _PLACEHOLDER_RE.search(template.replace(placeholder, "")):
        raise CannotRun("config-invalid: unsupported version template placeholder")
    prefix, suffix = template.split(placeholder, 1)
    return prefix, suffix


def _validate_location(location: VersionLocation) -> None:
    """Reject a location whose selector cannot provide an exact round trip."""
    if location.role not in _ROLE_SET:
        raise CannotRun(f"inventory-incomplete: unknown role {location.role!r}")
    if location.expected_count <= 0:
        raise CannotRun(f"inventory-incomplete: {location.path} expected_count must be positive")
    if not location.selector.strip():
        raise CannotRun(f"unsupported-extraction: {location.path} has no selector")
    search_prefix, search_suffix = _template_parts(location.search, "{current_version}")
    replace_prefix, replace_suffix = _template_parts(location.replace, "{new_version}")
    if not search_prefix and not search_suffix:
        raise CannotRun(f"unsupported-extraction: {location.path} selector is too broad")
    if (search_prefix, search_suffix) != (replace_prefix, replace_suffix):
        raise CannotRun(f"unsupported-extraction: {location.path} replacement changes text outside the version token")
    if "\r" in location.search or "\r" in location.replace:
        raise CannotRun(f"unsupported-extraction: {location.path} has unsupported carriage returns")
    if location.role in {"metadata", "source"} and not _ASSIGNMENT_RE.search(location.search):
        raise CannotRun(
            f"unsupported-extraction: {location.role} selector for {location.path} must target a literal assignment"
        )
    if location.role == "documentation":
        marker = location.selector.casefold() + " " + location.search.casefold()
        if "project-version" not in marker and "project version" not in marker:
            raise CannotRun(
                f"unsupported-extraction: documentation selector for {location.path} is not marked project-version"
            )


def _section_location(parser: configparser.RawConfigParser, section: str) -> VersionLocation | None:
    """Derive a location from a bumpversion-compatible or adapter section."""
    match = _SECTION_RE.fullmatch(section)
    if match:
        role = match.group("role")
        path = match.group("path")
    else:
        match = _PROJECT_SECTION_RE.fullmatch(section)
        if not match:
            return None
        role = match.group("role")
        path = match.group("path")
    if role is None or not role.strip():
        raise CannotRun(f"inventory-incomplete: {section} must declare metadata, source or documentation role")
    role = role.strip()
    path = _safe_relative_path(path.strip(), what="location")
    options = parser[section]
    try:
        search = options["search"]
        replace = options["replace"]
    except KeyError as exc:
        raise CannotRun(f"config-invalid: {section} requires search and replace templates") from exc
    selector = options.get("selector", search).strip()
    count_value = options.get("expected_count", options.get("count", "1"))
    try:
        expected_count = int(count_value)
    except (TypeError, ValueError) as exc:
        raise CannotRun(f"inventory-incomplete: {path} requires a positive expected_count") from exc
    location = VersionLocation(
        path=path,
        role=role,
        selector=selector,
        search=search,
        replace=replace,
        expected_count=expected_count,
    )
    _validate_location(location)
    return location


def parse_inventory(
    config_text: str,
    *,
    config_path: str = ".config/bumpversion.cfg",
    config_digest: str = "",
    snapshot: str = "",
) -> ProjectVersionInventory:
    """Parse one config into a complete three-role inventory.

    ``config_text`` is supplied by a selected Git blob by the gate.  Keeping
    this parser pure makes malformed and incomplete declarations testable
    without importing a target project or touching its worktree.
    """
    if len(config_text.encode("utf-8")) > _MAX_CONFIG_BYTES:
        raise CannotRun("config-invalid: bumpversion configuration exceeds the size bound")
    config_path = _safe_relative_path(config_path, what="configuration")
    parser = configparser.RawConfigParser(interpolation=None, strict=True)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    try:
        parser.read_string(config_text)
    except (configparser.Error, ValueError) as exc:
        raise CannotRun("config-invalid: malformed bumpversion configuration") from exc
    if not parser.has_section("bumpversion"):
        raise CannotRun("config-invalid: missing [bumpversion] section")
    current_version = parser.get("bumpversion", "current_version", fallback="").strip()
    if not current_version or not _SAFE_VERSION_RE.fullmatch(current_version):
        raise CannotRun("config-invalid: current_version is missing or malformed")
    locations: list[VersionLocation] = []
    for section in parser.sections():
        location = _section_location(parser, section)
        if location is not None:
            locations.append(location)
    if not locations:
        raise CannotRun("inventory-incomplete: no role-declared bumpversion locations")
    paths = [location.path for location in locations]
    if len(set(paths)) != len(paths):
        raise CannotRun("inventory-incomplete: duplicate version locations")
    roles = {location.role for location in locations}
    missing = sorted(_ROLE_SET - roles)
    if missing:
        raise CannotRun(f"inventory-incomplete: missing role coverage ({', '.join(missing)})")
    if config_digest == "":
        config_digest = _sha256(config_text)
    return ProjectVersionInventory(
        current_version=current_version,
        locations=tuple(sorted(locations, key=lambda item: (item.role, item.path))),
        config_digest=config_digest,
        snapshot=snapshot,
        config_path=config_path,
    )


# Public alias used by callers that prefer the manifest terminology.
load_inventory = parse_inventory


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _extractor(location: VersionLocation) -> re.Pattern[str]:
    prefix, suffix = _template_parts(location.search, "{current_version}")
    capture = r"(?P<version>[^\s\r\n]+)" if not suffix else r"(?P<version>[^\s\r\n]+?)"
    return re.compile(re.escape(prefix) + capture + re.escape(suffix))


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def check_inventory(
    inventory: ProjectVersionInventory,
    contents: Mapping[str, str],
    *,
    blob_digests: Mapping[str, str] | None = None,
) -> tuple[VersionCheck, ...]:
    """Check every declared location against its canonical version.

    ``contents`` must be the selected Git snapshot, never worktree text.  A
    missing location or an unexpected number of matches is a typed refusal so
    no successful verdict can be emitted for an unchecked surface.
    """
    checks: list[VersionCheck] = []
    digests = blob_digests or {}
    for location in inventory.locations:
        if location.path not in contents:
            raise CannotRun(f"location-unreadable: missing Git blob {location.path}")
        text = contents[location.path]
        if len(text.encode("utf-8")) > _MAX_SOURCE_BYTES:
            raise CannotRun(f"location-unreadable: {location.path} exceeds the size bound")
        matches = tuple(_extractor(location).finditer(text))
        if len(matches) != location.expected_count:
            raise CannotRun(
                f"selector-ambiguous: {location.path} expected {location.expected_count} matches, found {len(matches)}"
            )
        blob_digest = digests.get(location.path, _sha256(text))
        for match in matches:
            actual = match.group("version")
            checks.append(
                VersionCheck(
                    location=location,
                    expected=inventory.current_version,
                    actual=actual,
                    line=_line(text, match.start()),
                    checked_count=len(matches),
                    expected_count=location.expected_count,
                    config_digest=inventory.config_digest,
                    blob_digest=blob_digest,
                    snapshot=inventory.snapshot,
                )
            )
    return tuple(sorted(checks, key=lambda item: (item.location.role, item.location.path, item.line)))


def _mode_for_path(root: Path, path: str, *, index: bool, ref: str | None) -> str:
    """Return a selected entry's mode and reject missing/non-regular entries."""
    if index:
        result = run_git(root, ("ls-files", "--stage", "--", path), preserve_index=True)
        if result.returncode != 0:
            raise CannotRun("snapshot-unavailable: could not inspect the index")
        rows = [row for row in result.stdout.splitlines() if row]
        if len(rows) != 1:
            raise CannotRun(f"location-unreadable: {path} is missing or conflicted in the index")
        mode = rows[0].split(" ", 1)[0]
    else:
        if ref is None:
            raise CannotRun("snapshot-unavailable: no selected commit")
        result = run_git(root, ("ls-tree", ref, "--", path))
        if result.returncode != 0:
            raise CannotRun("snapshot-unavailable: could not inspect the selected commit")
        rows = [row for row in result.stdout.splitlines() if row]
        if len(rows) != 1:
            raise CannotRun(f"location-unreadable: {path} is missing or ambiguous in the selected commit")
        mode = rows[0].split(" ", 1)[0]
    if mode not in {"100644", "100755"}:
        raise CannotRun(f"location-unreadable: {path} is not a regular Git file")
    return mode


def _selected_blob(root: Path, path: str, *, index: bool, ref: str | None) -> tuple[str, str]:
    _mode_for_path(root, path, index=index, ref=ref)
    spec = f":{path}" if index else f"{ref}:{path}"
    try:
        text = blob_text(root, spec)
    except CannotRun as exc:
        raise CannotRun(f"location-unreadable: could not read Git blob {path}") from exc
    if text is None:
        raise CannotRun(f"location-unreadable: {path} is absent from the selected snapshot")
    return text, _sha256(text)


def _snapshot(root: Path, *, index: bool, ref: str | None) -> str:
    try:
        if index:
            tree = git_text(root, ("write-tree",), preserve_index=True).strip()
            if not tree:
                raise CannotRun("snapshot-unavailable: index has no tree identity")
            return f"index-tree:{tree}"
        if ref is None:
            raise CannotRun("snapshot-unavailable: selected commit is absent")
        commit = git_text(root, ("rev-parse", ref)).strip()
        tree = git_text(root, ("rev-parse", f"{ref}^{{tree}}")).strip()
        return f"commit:{commit}:tree:{tree}"
    except CannotRun as exc:
        if str(exc).startswith("snapshot-unavailable:"):
            raise
        raise CannotRun("snapshot-unavailable: selected Git snapshot is unreadable") from exc
    except (OSError, UnicodeError) as exc:
        raise CannotRun("snapshot-unavailable: selected Git snapshot is unreadable") from exc


def _config_is_effective(text: str) -> bool:
    return bool(re.search(r"(?m)^\[bumpversion\][ \t]*$", text))


def _selected_configuration(
    root: Path,
    config_path: str,
    *,
    index: bool,
    ref: str | None,
) -> tuple[str, str, str]:
    """Read one config and reject competing effective authorities."""
    try:
        selected_text, selected_digest = _selected_blob(root, config_path, index=index, ref=ref)
    except CannotRun as exc:
        if not _path_present(root, config_path, index=index, ref=ref):
            raise CannotRun(f"config-missing: canonical configuration {config_path} is absent") from exc
        raise
    effective: list[str] = []
    if _config_is_effective(selected_text):
        effective.append(config_path)
    for candidate in _CONFIG_CANDIDATES:
        if candidate == config_path:
            continue
        try:
            text, _ = _selected_blob(root, candidate, index=index, ref=ref)
        except CannotRun:
            if not _path_present(root, candidate, index=index, ref=ref):
                continue
            raise
        if _config_is_effective(text):
            effective.append(candidate)
    if config_path not in effective:
        raise CannotRun("config-invalid: selected configuration has no effective [bumpversion] authority")
    if len(effective) != 1:
        raise CannotRun(f"config-ambiguous: competing bumpversion configurations ({', '.join(sorted(effective))})")
    return selected_text, selected_digest, config_path


def _path_present(root: Path, path: str, *, index: bool, ref: str | None) -> bool:
    """Return whether a selected Git tree contains ``path`` at all."""
    if index:
        result = run_git(root, ("ls-files", "--stage", "--", path), preserve_index=True)
    else:
        if ref is None:
            raise CannotRun("snapshot-unavailable: no selected commit")
        result = run_git(root, ("ls-tree", ref, "--", path))
    if result.returncode != 0:
        raise CannotRun(f"snapshot-unavailable: could not inspect selected path {path}")
    return bool([row for row in result.stdout.splitlines() if row])


def evaluate(
    root: Path, *, config_path: str, base_ref: str | None = None
) -> tuple[ProjectVersionInventory, tuple[VersionCheck, ...]]:
    """Evaluate the selected Git snapshot and return inventory plus observations."""
    try:
        root = repo_root(root)
        _changed, _before, after = comparison(root, explicit=base_ref)
    except CannotRun as exc:
        if str(exc).startswith("snapshot-unavailable:"):
            raise
        raise CannotRun(f"snapshot-unavailable: could not select a Git snapshot ({exc})") from exc
    index = after == ""
    selected_ref = None if index else (after or "HEAD")
    snapshot = _snapshot(root, index=index, ref=selected_ref)
    config_path = _safe_relative_path(config_path, what="configuration")
    config_text, config_digest, _ = _selected_configuration(root, config_path, index=index, ref=selected_ref)
    inventory = parse_inventory(
        config_text,
        config_path=config_path,
        config_digest=config_digest,
        snapshot=snapshot,
    )
    contents: dict[str, str] = {}
    digests: dict[str, str] = {}
    for location in inventory.locations:
        text, digest = _selected_blob(root, location.path, index=index, ref=selected_ref)
        contents[location.path] = text
        digests[location.path] = digest
    return inventory, check_inventory(inventory, contents, blob_digests=digests)


def _render_check(check: VersionCheck) -> str:
    return (
        f"{check.role} {check.path}:{check.line}: {check.status}; "
        f"expected={check.expected!r} actual={check.actual!r}; "
        f"selector={check.location.selector!r}; "
        f"checked={check.checked_count}/{check.expected_count}; "
        f"config={check.config_digest}; blob={check.blob_digest}; snapshot={check.snapshot}"
    )


def main(argv: list[str]) -> int:
    """Run the offline exact-project-version gate."""
    parser = argparse.ArgumentParser(prog="project-version-sync", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--config",
        default=".config/bumpversion.cfg",
        help="repository-relative canonical bumpversion configuration",
    )
    parser.add_argument("--base-ref", default=None, help="committed base/ref selection for CI or range checks")
    args = parser.parse_args(argv)
    inventory, checks = evaluate(args.root, config_path=args.config, base_ref=args.base_ref)
    mismatches = [check for check in checks if check.status != "pass"]
    for check in checks:
        print(f"project-version-sync: {_render_check(check)}")
    if mismatches:
        print(f"project-version-sync: version-mismatch ({len(mismatches)} location(s))")
        return 1
    print(
        f"project-version-sync: PASS; current={inventory.current_version!r}; "
        f"locations={len(inventory.locations)}; checked={len(checks)}; roles={','.join(ROLES)}; "
        f"config={inventory.config_digest}; snapshot={inventory.snapshot}"
    )
    return 0
