"""Repository ownership independent of branch names and checkout locations."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from pipelines_hooks.core.gitenv import git_text


def _remote_name(url: str) -> str | None:
    """Extract a repository slug from URL, SCP-style, or local git remotes."""
    try:
        path = urlsplit(url).path if "://" in url else url.split(":", 1)[-1]
    except ValueError:
        return None
    name = path.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    return name if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name) else None


def remote_owner(repo: Path) -> str | None:
    """Prefer origin; without it, accept only a sole remote. Never contact it."""
    remotes = git_text(repo, ("remote",)).splitlines()
    remote = "origin" if "origin" in remotes else remotes[0] if len(remotes) == 1 else None
    if remote is None:
        return None
    return _remote_name(git_text(repo, ("remote", "get-url", remote)).strip())
