"""Project test-layout policy and source inventory for PIPE-PAGES-R039.1-.6."""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
import tomllib
from contextlib import contextmanager
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text
from pipelines_hooks.kiss.runner import materialize_index

DEFAULT_SHUFFLE_SEEDS = (1729, 7919)
DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_TIMEOUT_SECONDS = 600.0
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_PROJECTS = 64
MAX_TESTS = 2_000
MAX_STATE_FILES = 10_000
MAX_FILE_BYTES = 8 * 1024 * 1024
TEST_PATTERNS = ("test_*.py", "*_test.py")


def _strings(value: object, name: str, *, required: bool = True) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise CannotRun(f"test-layout {name} must be a list of non-empty strings")
    result = tuple(item.strip() for item in value)
    if required and not result:
        raise CannotRun(f"test-layout {name} must not be empty")
    if len(set(result)) != len(result):
        raise CannotRun(f"test-layout {name} contains duplicates")
    return result


def _safe_relative(value: str, label: str) -> str:
    path = Path(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise CannotRun(f"test-layout {label} must be a contained relative path")
    return path.as_posix()


@dataclass(frozen=True)
class ProjectLayout:
    """One project's declared test roots, fixtures, and reset boundaries."""

    name: str
    root: str
    unit_module_roots: tuple[str, ...]
    integration_module_roots: tuple[str, ...]
    shared_fixture_locations: tuple[str, ...]
    required_category_modules: tuple[str, ...]
    isolation_boundaries: tuple[str, ...]
    reset_contracts: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProjectLayout":
        name = value.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CannotRun("test-layout project name must be a non-empty string")
        roots = ("unit_module_roots", "integration_module_roots")
        optional = ("shared_fixture_locations", "required_category_modules", "isolation_boundaries", "reset_contracts")
        missing = [key for key in (*roots, *optional) if key not in value]
        if missing:
            raise CannotRun(f"test-layout project {name!r} omits declarations: {', '.join(missing)}")
        fields = {key: _strings(value.get(key), key) for key in roots}
        fields.update({key: _strings(value.get(key), key, required=False) for key in optional})
        raw_root = value.get("root", ".")
        if not isinstance(raw_root, str):
            raise CannotRun(f"test-layout {name}.root must be a relative string")
        root = _safe_relative(raw_root, f"{name}.root") if raw_root != "." else "."
        if not fields["isolation_boundaries"]:
            raise CannotRun(f"test-layout project {name!r} declares no isolation boundaries")
        if not fields["reset_contracts"]:
            raise CannotRun(f"test-layout project {name!r} declares no reset contracts")
        return cls(name=name.strip(), root=root, **fields)


@dataclass(frozen=True)
class TestLayoutPolicy:
    """Validated policy shared by inventory discovery and the order probe."""

    __test__ = False

    projects: tuple[ProjectLayout, ...]
    shuffle_seeds: tuple[int, int] = DEFAULT_SHUFFLE_SEEDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    version: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TestLayoutPolicy":
        payload = value.get("test_layout", value)
        if not isinstance(payload, Mapping):
            raise CannotRun("test-layout policy must be a table")
        version = payload.get("version", 1)
        if version != 1:
            raise CannotRun(f"test-layout policy version is unsupported: {version!r}")
        raw_projects = payload.get("projects")
        if not isinstance(raw_projects, (list, tuple)) or not raw_projects or len(raw_projects) > MAX_PROJECTS:
            raise CannotRun(f"test-layout projects must contain 1..{MAX_PROJECTS} entries")
        projects = tuple(ProjectLayout.from_mapping(item) for item in raw_projects if isinstance(item, Mapping))
        if len(projects) != len(raw_projects):
            raise CannotRun("test-layout projects must be tables")
        if len({project.name for project in projects}) != len(projects):
            raise CannotRun("test-layout project names must be unique")
        seeds = payload.get("shuffle_seeds", list(DEFAULT_SHUFFLE_SEEDS))
        if (
            not isinstance(seeds, (list, tuple))
            or len(seeds) != 2
            or any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds)
        ):
            raise CannotRun("test-layout shuffle_seeds must contain exactly two integers")
        if len(set(seeds)) != 2:
            raise CannotRun("test-layout shuffle_seeds must contain two distinct integers")
        timeout = payload.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or timeout <= 0
            or timeout > MAX_TIMEOUT_SECONDS
        ):
            raise CannotRun(f"test-layout timeout_seconds must be in (0, {MAX_TIMEOUT_SECONDS:g}]")
        return cls(
            projects=projects, shuffle_seeds=(seeds[0], seeds[1]), timeout_seconds=float(timeout), version=version
        )


def load_policy(path: Path) -> TestLayoutPolicy:
    """Load one JSON or TOML policy, refusing absent or malformed input."""
    if path.suffix not in {".json", ".toml"}:
        raise CannotRun(f"test-layout policy format is unsupported: {path.suffix or '<none>'}")
    try:
        raw = path.read_bytes()
        value: object = json.loads(raw) if path.suffix == ".json" else tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read test-layout policy {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise CannotRun("test-layout policy root must be a table")
    return TestLayoutPolicy.from_mapping(value)


def _digest_bytes(items: Sequence[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(items):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def policy_digest(policy: TestLayoutPolicy) -> str:
    """Stable identity for the accepted policy, suitable for receipts."""
    payload = {
        "version": policy.version,
        "shuffle_seeds": policy.shuffle_seeds,
        "timeout_seconds": policy.timeout_seconds,
        "projects": [project.__dict__ for project in policy.projects],
    }
    return _digest_bytes([("policy.json", json.dumps(payload, sort_keys=True).encode("utf-8"))])


def _project_path(root: Path, project: ProjectLayout) -> Path:
    path = (root / project.root).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_dir():
        raise CannotRun(f"test-layout project root is unavailable: {project.name}: {project.root}")
    return path


@contextmanager
def selected_source(root: Path) -> Iterator[tuple[Path, str]]:
    """Materialize the selected index as an exact, disposable source tree.

    A hook may expose a temporary ``GIT_INDEX_FILE`` while the worktree holds
    unrelated edits.  ``checkout-index`` reads that selected index and keeps
    its blob bytes and modes; no gate inventory is allowed to read the dirty
    worktree as a substitute.  ``write-tree`` supplies a stable source
    identity for evidence without creating a commit.
    """
    with tempfile.TemporaryDirectory(prefix="pipelines-test-layout-source-") as temporary:
        snapshot = Path(temporary) / "source"
        materialize_index(root, snapshot)
        tree = git_text(root, ("write-tree",), preserve_index=True).strip()
        if not tree:
            raise CannotRun("test-layout selected Git index has no tree identity")
        yield snapshot, f"index:{tree}"


def _declared_path(project_root: Path, value: str, label: str) -> Path:
    path = (project_root / value).resolve()
    if not path.is_relative_to(project_root.resolve()):
        raise CannotRun(f"test-layout {label} escapes project root: {value}")
    return path


def _files_under(path: Path, project_root: Path, patterns: tuple[str, ...]) -> tuple[str, ...]:
    if not path.is_dir():
        raise CannotRun(f"test-layout declared module root is unavailable: {path.relative_to(project_root)}")
    found: set[str] = set()
    for pattern in patterns:
        candidates = sorted(path.rglob(pattern))
        for candidate in candidates:
            if candidate.is_file() and not candidate.is_symlink():
                found.add(candidate.relative_to(project_root).as_posix())
    return tuple(sorted(found))


def _fixture_files(path: Path, project_root: Path) -> tuple[str, ...]:
    if path.is_file():
        return (path.relative_to(project_root).as_posix(),)
    files = [candidate for candidate in path.rglob("*") if candidate.is_file() and not candidate.is_symlink()]
    if len(files) > MAX_STATE_FILES:
        raise CannotRun(f"test-layout fixture inventory exceeds {MAX_STATE_FILES}: {path.relative_to(project_root)}")
    return tuple(sorted(candidate.relative_to(project_root).as_posix() for candidate in files))


def _fixture_declared(path: str, declared: tuple[str, ...]) -> bool:
    return any(path == value or path.startswith(value.rstrip("/") + "/") for value in declared)


@dataclass(frozen=True)
class ProjectInventory:
    """Measured project layout before any test-order execution."""

    project: ProjectLayout
    unit_modules: tuple[str, ...]
    integration_modules: tuple[str, ...]
    fixtures: tuple[str, ...]
    required_modules: tuple[str, ...]
    test_files: tuple[str, ...]
    source_digest: str


def _inventory_project(source_root: Path, project: ProjectLayout) -> ProjectInventory:
    """Discover declared source, fixtures, and all test files for one project."""
    project_root = _project_path(source_root, project)
    unit = tuple(
        path
        for name in project.unit_module_roots
        for path in _files_under(
            _declared_path(project_root, name, f"{project.name}.unit_module_roots"), project_root, ("*.py",)
        )
    )
    integration = tuple(
        path
        for name in project.integration_module_roots
        for path in _files_under(
            _declared_path(project_root, name, f"{project.name}.integration_module_roots"), project_root, ("*.py",)
        )
    )
    fixtures: list[str] = []
    fixture_files: list[str] = []
    for name in project.shared_fixture_locations:
        path = _declared_path(project_root, name, f"{project.name}.shared_fixture_locations")
        if not path.exists() or path.is_symlink():
            raise CannotRun(f"test-layout required fixture is unavailable: {project.name}: {name}")
        fixtures.append(name)
        fixture_files.extend(_fixture_files(path, project_root))
    required: list[str] = []
    for name in project.required_category_modules:
        path = _declared_path(project_root, name, f"{project.name}.required_category_modules")
        if not path.is_file() or path.is_symlink():
            raise CannotRun(f"test-layout required module is unavailable: {project.name}: {name}")
        required.append(name)
    tests = tuple(
        sorted(
            path
            for path in set(unit + integration)
            if Path(path).name.startswith("test_") or Path(path).name.endswith("_test.py")
        )
    )
    if len(tests) > MAX_TESTS:
        raise CannotRun(f"test-layout collected tests exceed {MAX_TESTS}: {project.name}")
    if not tests:
        raise CannotRun(f"test-layout collected no tests for project: {project.name}")
    discovered = set(fixture_files)
    for relative in unit + integration:
        if Path(relative).name == "conftest.py" or any(
            part.casefold() in {"fixture", "fixtures"} for part in Path(relative).parts
        ):
            discovered.add(relative)
    undeclared = sorted(path for path in discovered if not _fixture_declared(path, tuple(fixtures)))
    if undeclared:
        raise CannotRun(f"test-layout fixture is outside project inventory: {project.name}: {', '.join(undeclared)}")
    source_paths = sorted(set(unit + integration + tuple(fixture_files) + tuple(required)))
    items = []
    for relative in source_paths:
        path = project_root / relative
        if path.is_file():
            if path.stat().st_size > MAX_FILE_BYTES:
                raise CannotRun(f"test-layout source exceeds {MAX_FILE_BYTES} bytes: {relative}")
            items.append((relative, path.read_bytes()))
    return ProjectInventory(project, unit, integration, tuple(fixtures), tuple(required), tests, _digest_bytes(items))


def inventory_project(root: Path, project: ProjectLayout, *, source_root: Path | None = None) -> ProjectInventory:
    """Inventory an exact selected source tree, materializing one when needed."""
    if source_root is not None:
        return _inventory_project(source_root, project)
    with selected_source(root) as (snapshot, _source_ref):
        return _inventory_project(snapshot, project)


def _policy_path(root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit if explicit.is_absolute() else root / explicit
    for candidate in (root / ".config/test-layout.json", root / ".config/test-layout.toml"):
        if candidate.is_file():
            return candidate
    raise CannotRun("test-layout policy is unavailable; provide --inventory")


def policy_path_in_source(root: Path, source_root: Path, explicit: Path | None) -> Path:
    """Map a repository-relative policy path onto the selected source tree."""
    policy = _policy_path(root, explicit)
    try:
        relative = policy.resolve().relative_to(root.resolve())
    except ValueError:
        return policy
    selected = source_root / relative
    if not selected.is_file():
        raise CannotRun(f"test-layout selected policy is unavailable: {relative.as_posix()}")
    return selected
