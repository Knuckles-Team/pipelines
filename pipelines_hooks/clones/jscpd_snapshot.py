"""Materialize committed trees with ``git archive`` for jscpd to scan.

Snapshots avoid handing jscpd a repository root (and its .git metadata) while
keeping hidden configuration such as ``.github``. No refs, worktrees, stashes,
commits or baseline files are created.
"""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from pipelines_hooks.clones.contract import is_jscpd_path
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, nul_split, sanitized_env


def tree_paths(root: Path, ref: str) -> list[str]:
    """Every blob path in a committed tree (submodules are not files)."""
    paths = []
    for record in nul_split(git_text(root, ("ls-tree", "-r", "-z", ref))):
        header, _, path = record.partition("\t")
        if len(header.split()) >= 2 and header.split()[1] == "blob":
            paths.append(path)
    return paths


def in_scope_paths(root: Path, ref: str) -> list[str]:
    return sorted(path for path in tree_paths(root, ref) if is_jscpd_path(path))


def _safe_member(member: tarfile.TarInfo, destination: Path) -> None:
    relative = PurePosixPath(member.name.replace("\\", "/"))
    unsafe = (
        "\x00" in member.name
        or not relative.parts
        or relative.is_absolute()
        or PureWindowsPath(member.name).drive
        or ".." in relative.parts
    )
    if unsafe or not (member.isdir() or member.isreg()):
        raise CannotRun(f"git archive contains an unsafe or unsupported entry {member.name!r}")
    target = (destination / Path(*relative.parts)).resolve(strict=False)
    if not target.is_relative_to(destination.resolve(strict=False)):
        raise CannotRun(f"git archive path escapes its destination: {member.name!r}")


def materialize(root: Path, ref: str, destination: Path) -> Path:
    """Unpack ``ref`` (a commit or tree id) under ``destination``."""
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination.parent / f"{destination.name}.tar"
    with archive.open("wb") as stream:
        result = subprocess.run(
            ["git", "archive", "--format=tar", ref], cwd=str(root), env=sanitized_env(),
            stdout=stream, stderr=subprocess.PIPE, timeout=900, check=False,
        )
    if result.returncode != 0:
        raise CannotRun(f"git archive {ref} failed: {result.stderr.decode(errors='replace')[:400]}")
    with tarfile.open(archive, mode="r:") as bundle:
        members = bundle.getmembers()
        for member in members:
            _safe_member(member, destination)
        bundle.extractall(destination, members=members, filter="data")
    return destination
