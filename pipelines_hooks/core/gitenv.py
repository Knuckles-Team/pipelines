"""Git access with ambient repository selectors removed.

A real ``git commit``/``git push`` exports ``GIT_DIR``, ``GIT_INDEX_FILE``,
``GIT_WORK_TREE`` and siblings into every hook it runs, and ``git -C`` does not
override them. Inherited blindly they re-root path resolution, which is how
copied gate helpers once measured an empty universe and reported a confident
clean verdict. Every child process here therefore gets an environment with
EVERY ``GIT_*`` variable removed; ``GIT_INDEX_FILE`` is retained only for a
caller that must read the index being committed.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.settings import process_environment

_INDEX_ENV = "GIT_INDEX_FILE"
GIT_TIMEOUT_SECONDS = 300


def sanitized_env(*, preserve_index: bool = False) -> dict[str, str]:
    """The process environment without any ambient repository selector."""
    environment = process_environment()
    for key in tuple(environment):
        if key.startswith("GIT_") and not (preserve_index and key == _INDEX_ENV):
            environment.pop(key)
    return environment


def run_git(
    root: Path, args: Sequence[str], *, preserve_index: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run git from ``root``; a process failure raises :class:`CannotRun`."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(root),
            env=sanitized_env(preserve_index=preserve_index),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"could not execute git {' '.join(args)}: {exc}") from exc


def git_text(
    root: Path, args: Sequence[str], *, preserve_index: bool = False
) -> str:
    """Standard output of a git command that must succeed."""
    result = run_git(root, args, preserve_index=preserve_index)
    if result.returncode != 0:
        detail = (result.stderr or "").strip()[:400]
        raise CannotRun(f"git {' '.join(args)} failed: {detail}")
    return result.stdout or ""


def nul_split(raw: str) -> list[str]:
    """Split NUL-framed git output; newlines are legal pathname bytes."""
    return [item for item in raw.split("\x00") if item]


def repo_root(start: Path) -> Path:
    """The work-tree root containing ``start``."""
    toplevel = git_text(start, ("rev-parse", "--show-toplevel")).strip()
    if not toplevel:
        raise CannotRun(f"{start} is not inside a git work tree")
    return Path(toplevel)


def has_head(root: Path) -> bool:
    """Whether the repository has a first commit yet."""
    return run_git(root, ("rev-parse", "--verify", "-q", "HEAD")).returncode == 0


def blob_text(root: Path, spec: str) -> str | None:
    """Text of ``HEAD:path``/``:path``, or ``None`` when the path is absent.

    Absence is proven with ``git cat-file -e`` so a failing ``git show`` is
    never mistaken for a newly added file.
    """
    if run_git(root, ("cat-file", "-e", spec), preserve_index=True).returncode != 0:
        return None
    return git_text(root, ("show", spec), preserve_index=True)


def staged_paths(root: Path) -> list[str]:
    """Paths staged as added, copied, modified or renamed."""
    raw = git_text(
        root,
        ("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"),
        preserve_index=True,
    )
    return sorted(set(nul_split(raw)))
