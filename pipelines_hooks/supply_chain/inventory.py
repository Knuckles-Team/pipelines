"""Discover repositories and their Git source inventory; classify inspected assets."""

from __future__ import annotations

import os
from pathlib import Path, PurePath, PurePosixPath

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import nul_split, run_git

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_REPOSITORIES = 1_000
MAX_DISCOVERY_DEPTH = 5
SKIP_DIRECTORIES = frozenset(
    {".cache", ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".venv", ".worktrees",
     "__pycache__", "dist", "node_modules", "target", "vendor"}
)
_INSTALLERS = frozenset({"bootstrap.ps1", "bootstrap.sh", "install.ps1", "install.sh", "setup.ps1", "setup.sh", "promote_local_release.py"})


def repository_label(repository: Path, fleet_root: Path) -> str:
    try:
        value = repository.relative_to(fleet_root).as_posix()
    except ValueError:
        return repository.name
    return repository.name if value == "." else value


def _child_directories(path: Path) -> list[Path]:
    try:
        entries = list(os.scandir(path))
    except OSError:
        raise CannotRun("repository discovery is unavailable") from None
    return sorted((Path(e.path) for e in entries if e.name not in SKIP_DIRECTORIES and e.is_dir(follow_symlinks=False)), reverse=True)


def discover_repositories(root: Path) -> tuple[Path, ...]:
    """``root`` itself when it is a repository, else nested repositories (bounded)."""
    root = root.resolve()
    found: list[Path] = []
    pending = [(root, 0)]
    while pending:
        current, depth = pending.pop()
        if (current / ".git").exists():
            found.append(current)
        elif depth < MAX_DISCOVERY_DEPTH:
            pending.extend((child, depth + 1) for child in _child_directories(current))
        if len(found) > MAX_REPOSITORIES:
            raise CannotRun("repository discovery exceeds the safe bound")
    return tuple(sorted(found))


def source_files(repository: Path) -> tuple[Path, ...]:
    """Tracked plus untracked non-ignored paths, rejecting unsafe entries."""
    result = run_git(repository, ("ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    if result.returncode != 0:
        raise CannotRun("Git source inventory is unavailable")
    paths = []
    for raw in nul_split(result.stdout):
        relative = PurePosixPath(raw)
        if relative.is_absolute() or ".." in relative.parts:
            raise CannotRun("Git source inventory contains an unsafe path")
        paths.append(repository.joinpath(*relative.parts))
    return tuple(paths)


def read_source(path: Path) -> str:
    if path.is_symlink():
        raise CannotRun("source file must not be a symlink")
    try:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise CannotRun("source file exceeds the safe inspection bound")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise CannotRun("source file is unreadable") from None


def asset_kinds(relative: PurePath) -> tuple[str, ...]:
    """Which rule families apply: workflow, precommit, docker, compose, installer."""
    name = relative.name.casefold()
    suffix = relative.suffix.casefold()
    kinds = {
        "workflow": len(relative.parts) >= 3 and relative.parts[-3:-1] == (".github", "workflows") and suffix in {".yml", ".yaml"},
        "precommit": relative.name == ".pre-commit-config.yaml",
        "docker": name == "dockerfile" or name.startswith("dockerfile.") or name.endswith(".dockerfile"),
        "compose": suffix in {".yml", ".yaml"} and ("compose" in name or name.endswith((".stack.yml", ".stack.yaml"))),
        "installer": name in _INSTALLERS,
    }
    return tuple(kind for kind, applies in kinds.items() if applies)
