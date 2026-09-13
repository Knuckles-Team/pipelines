"""Resolve the base revision a differential gate compares against."""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, run_git
from pipelines_hooks.core.settings import setting

ZERO_SHA = "0" * 40


def commit(root: Path, ref: str) -> str | None:
    """The full commit id of ``ref``, or ``None`` when it does not resolve."""
    if not ref or ref.startswith("-") or "\x00" in ref:
        raise CannotRun(f"base ref must be a revision, not an option: {ref!r}")
    result = run_git(root, ("rev-parse", "--verify", "-q", "--end-of-options", f"{ref}^{{commit}}"))
    value = (result.stdout or "").strip()
    return value if result.returncode == 0 and value else None


def _pushed_from(root: Path) -> str | None:
    value = setting("PRE_COMMIT_FROM_REF")
    return commit(root, value) if value and value != ZERO_SHA else None


def upstream_base(root: Path, explicit: str | None) -> str | None:
    """The widest honest "not yet published" base, or ``None`` for all history.

    An explicit ref, then the remote revision pre-commit is pushing over, then
    ``origin/main``. With none of them the whole history is unpublished, and
    ``None`` tells the caller to scan all of it rather than guess a range.
    """
    if explicit:
        resolved = commit(root, explicit)
        if resolved is None:
            raise CannotRun(f"base ref {explicit!r} does not resolve to a commit")
        return resolved
    return _pushed_from(root) or commit(root, "origin/main")


def change_base(root: Path, explicit: str | None) -> str | None:
    """The base of a clone differential: upstream, else ``main``, else ``HEAD^``.

    ``None`` means the repository has a single commit and every pair is new.
    """
    base = upstream_base(root, explicit or setting("CX_DUP_BASE_REF") or None)
    head = git_text(root, ("rev-parse", "HEAD")).strip()
    for candidate in (base, commit(root, "main"), commit(root, "HEAD^")):
        if candidate is not None and candidate != head:
            return candidate
    return None
