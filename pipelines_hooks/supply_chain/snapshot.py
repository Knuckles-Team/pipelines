"""Source-snapshot mode: inventory workspace-declared provider roots without Git."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.supply_chain.inventory import MAX_SOURCE_BYTES, SKIP_DIRECTORIES
from pipelines_hooks.supply_chain.snapshot_workspace import workspace_provider_names

MAX_SNAPSHOT_ENTRIES = 200_000
MAX_SNAPSHOT_FILES = 100_000
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024 * 1024
MAX_SNAPSHOT_DEPTH = 32
#: Editable-sibling links materialized by the uv workspace helper: build plumbing, root only.
_WORKSPACE_SIBLINGS = ".uv-workspace-siblings"


@dataclass
class SnapshotBudget:
    entries: int = 0
    files: int = 0
    bytes: int = 0

    def entry(self, depth: int) -> None:
        self.entries += 1
        if self.entries > MAX_SNAPSHOT_ENTRIES or depth > MAX_SNAPSHOT_DEPTH:
            raise CannotRun("source snapshot entry count or depth exceeds the safe bound")

    def file(self, size: int) -> None:
        self.files, self.bytes = self.files + 1, self.bytes + size
        if size > MAX_SOURCE_BYTES or self.files > MAX_SNAPSHOT_FILES or self.bytes > MAX_SNAPSHOT_BYTES:
            raise CannotRun("source snapshot files exceed the safe bound")


def _is_checkout(root: Path, name: str) -> bool:
    try:
        mode = (root / name / ".git").lstat().st_mode
    except FileNotFoundError:
        return False
    except OSError:
        raise CannotRun("source snapshot membership is unavailable") from None
    return not stat.S_ISLNK(mode) and (stat.S_ISDIR(mode) or stat.S_ISREG(mode))


def _authoritative_root(providers_root: Path, workspace: Path) -> Path:
    """The resolved provider root, when it is a real directory owning ``workspace``."""
    try:
        root = providers_root.resolve(strict=True)
        expected = (root / "repository-manager" / "repository_manager" / "workspace.yml").resolve(strict=True)
        authoritative = workspace.resolve(strict=True) == expected
    except OSError:
        raise CannotRun("source snapshot root is unavailable") from None
    if providers_root.is_symlink() or not root.is_dir() or not authoritative:
        raise CannotRun("source snapshot root or workspace is not authoritative")
    return root


def resolve_snapshot_repositories(providers_root: Path, workspace: Path) -> tuple[Path, tuple[Path, ...]]:
    """Exactly the direct provider roots the authoritative workspace declares."""
    root = _authoritative_root(providers_root, workspace)
    try:
        directories = {e.name for e in os.scandir(root) if e.name not in SKIP_DIRECTORIES and e.is_dir(follow_symlinks=False)}
    except OSError:
        raise CannotRun("source snapshot membership is unavailable") from None
    providers = workspace_provider_names(workspace)
    unexpected = [name for name in directories - set(providers) if not _is_checkout(root, name)]
    if unexpected or not set(providers) <= directories:
        raise CannotRun("source snapshot provider membership is not exact")
    return root, tuple(root / name for name in providers)


def _classify_entry(entry: os.DirEntry[str], *, depth: int, budget: SnapshotBudget) -> str:
    try:
        metadata = entry.stat(follow_symlinks=False)
    except OSError:
        raise CannotRun("source snapshot entry is unavailable") from None
    budget.entry(depth)
    if stat.S_ISLNK(metadata.st_mode) or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
        raise CannotRun("source snapshot contains a symlink or special file")
    if stat.S_ISDIR(metadata.st_mode):
        return "dir"
    budget.file(metadata.st_size)
    return "file"


def snapshot_source_files(repository: Path, budget: SnapshotBudget) -> tuple[Path, ...]:
    """Every regular file below one provider, depth-first, never following links."""
    paths: list[Path] = []
    pending = [(repository, 0)]
    while pending:
        current, depth = pending.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name)
        except OSError:
            raise CannotRun("source snapshot inventory is unavailable") from None
        directories = []
        for entry in entries:
            kind = _classify_entry(entry, depth=depth + 1, budget=budget)
            skip = entry.name in SKIP_DIRECTORIES or (current == repository and entry.name == _WORKSPACE_SIBLINGS)
            directories.extend([(Path(entry.path), depth + 1)] if kind == "dir" and not skip else [])
            paths.extend([Path(entry.path)] if kind == "file" else [])
        pending.extend(reversed(directories))
    return tuple(paths)


def read_snapshot_bytes(path: Path) -> bytes:
    """One inventoried regular file, opened without following a symlink."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as stream:
            regular = stat.S_ISREG(os.fstat(stream.fileno()).st_mode)
            content = stream.read(MAX_SOURCE_BYTES + 1)
    except OSError:
        raise CannotRun("source snapshot file is unreadable") from None
    if not regular or len(content) > MAX_SOURCE_BYTES:
        raise CannotRun("source snapshot entry is not a bounded regular file")
    return content


def read_snapshot_source(path: Path) -> str:
    try:
        return read_snapshot_bytes(path).decode("utf-8")
    except UnicodeError:
        raise CannotRun("source snapshot file is unreadable") from None
