"""Tracked-file discovery that is immune to the ambient git environment.

A raw ``rglob`` also picks up gitignored, generated output that can carry a
stale copy of an already-fixed file, so gates prefer the git-tracked set.
Paths are anchored at the repository root and rebuilt as ``root / line``,
which is correct under both a plain and a hook-polluted invocation.
"""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.core.gitenv import git_text, nul_split, run_git

#: Directory names no source gate ever scans.
SKIP_DIRECTORIES = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".tox"}
)


def tracked_paths(root: Path, pathspecs: tuple[str, ...] = ()) -> list[str]:
    """Every tracked path (repository-relative), failing closed on git errors."""
    raw = git_text(root, ("ls-files", "-z", "--", *pathspecs), preserve_index=True)
    return nul_split(raw)


def _pathspecs(target: Path, root: Path, patterns: tuple[str, ...]) -> list[str]:
    relative = target.relative_to(root).as_posix()
    prefix = "" if relative == "." else f"{relative}/"
    if patterns:
        return [f"{prefix}{pattern}" for pattern in patterns]
    return [prefix] if prefix else ["."]


def _walked(target: Path, patterns: tuple[str, ...]) -> list[Path]:
    found = (
        [path for pattern in patterns for path in target.rglob(pattern)]
        if patterns
        else list(target.rglob("*"))
    )
    return sorted(path for path in found if path.is_file())


def tracked_or_walked(target: Path, patterns: tuple[str, ...], *, root: Path) -> list[Path]:
    """Files under ``target`` (matching ``patterns``), preferring the tracked set.

    Falls back to a filesystem walk only when ``target`` is outside ``root``
    or not inside a git work tree (a synthetic fixture), or when git knows no
    file there.
    """
    try:
        specs = _pathspecs(target, root, patterns)
    except ValueError:
        return _walked(target, patterns)
    result = run_git(root, ("ls-files", "-z", "--", *specs), preserve_index=True)
    tracked = [root / line for line in nul_split(result.stdout or "")]
    if result.returncode == 0 and tracked:
        return [path for path in tracked if path.is_file()]
    return _walked(target, patterns)


def skipped(path: Path) -> bool:
    """Whether any component of ``path`` is a never-scanned directory."""
    return any(part in SKIP_DIRECTORIES for part in path.parts)
