"""Resolve the git identity a commit was, or is about to be, made under.

Every call goes through :mod:`pipelines_hooks.core.gitenv`, which strips every
ambient ``GIT_*`` environment variable first, so the identity reported here is
always the one git itself would use (its config, not an inherited selector
that could spoof a different author/committer into the result).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text
from pipelines_hooks.identity.allowlist import Identity

_IDENT_RE = re.compile(r"^(?P<name>.*) <(?P<email>[^>]*)>")


@dataclass(frozen=True)
class CommitIdentity:
    """One commit's recorded author and committer identity."""

    sha: str
    author: Identity
    committer: Identity


def _parsed_identity(raw: str, *, field: str) -> Identity:
    match = _IDENT_RE.match(raw.strip())
    if not match:
        raise CannotRun(f"could not parse the git-resolved {field} identity")
    return Identity(name=match.group("name"), email=match.group("email"))


def pending_identity(root: Path) -> tuple[Identity, Identity]:
    """The author/committer identity git would resolve for a new commit right now."""
    author = _parsed_identity(git_text(root, ("var", "GIT_AUTHOR_IDENT")), field="author")
    committer = _parsed_identity(git_text(root, ("var", "GIT_COMMITTER_IDENT")), field="committer")
    return author, committer


def range_identities(root: Path, base: str | None) -> tuple[CommitIdentity, ...]:
    """Every commit's recorded author/committer identity in ``base..HEAD``.

    ``base`` of ``None`` means no base resolved and the full history is
    unpublished, matching :func:`pipelines_hooks.core.baseref.upstream_base`.
    """
    rev_range = f"{base}..HEAD" if base else "HEAD"
    raw = git_text(root, ("log", "--format=%H%x00%an%x00%ae%x00%cn%x00%ce", rev_range))
    commits = []
    for line in raw.splitlines():
        if not line:
            continue
        sha, author_name, author_email, committer_name, committer_email = line.split("\x00")
        commits.append(
            CommitIdentity(
                sha=sha,
                author=Identity(name=author_name, email=author_email),
                committer=Identity(name=committer_name, email=committer_email),
            )
        )
    return tuple(commits)
