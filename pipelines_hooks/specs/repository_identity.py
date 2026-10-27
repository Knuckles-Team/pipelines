"""Repository ownership independent of branch names and checkout locations."""

from __future__ import annotations

import re
import tomllib
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from pipelines_hooks.core.gitenv import git_text
from pipelines_hooks.core.repositories import repository_slug

_DECLARED_REPOSITORY = ("tool", "pipelines_hooks", "public_surface", "repository")
_OWNER_PREFIXES = {
    "ARBORA": "arbora",
    "AU": "meristem",
    "EG": "medulla",
    "GENIUSBOT": "axil",
    "PIPE": "pipelines",
    "SDK": "scion-sdk",
    "TUI": "tuig",
    "WEBUI": "overstory",
}
_SPEC_PREFIX = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9]*)-[A-Z][A-Z0-9-]*(?:-R[0-9]{3})?")


def _remote_name(url: str) -> str | None:
    """Extract a repository slug from URL, SCP-style, or local git remotes."""
    try:
        path = urlsplit(url).path if "://" in url else url.split(":", 1)[-1]
    except ValueError:
        return None
    name = path.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    return name if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name) else None


def _declared_public_surface(repo: Path) -> str | None:
    """Read the repository identity declaration carried by shared hook config."""
    path = repo / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return None
    value: object = document
    for key in _DECLARED_REPOSITORY:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return repository_slug(value) if isinstance(value, str) else None


def _declared_owner_prefix(repo: Path) -> str | None:
    """Resolve a first-party owner from the repository's own spec IDs."""
    paths = [repo / "specs" / "README.md"]
    paths.extend(sorted((repo / "specs").glob("*/requirements.md")))
    paths.extend(sorted((repo / "specs").glob("*/spec.md")))
    counts: Counter[str] = Counter()
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for match in _SPEC_PREFIX.finditer(text):
            prefix = match.group(1)
            if prefix in _OWNER_PREFIXES:
                counts[prefix] += 1
    if not counts:
        return None
    prefix, count = counts.most_common(1)[0]
    if count < 2 or sum(1 for item in counts if counts[item] == count) > 1:
        return None
    return _OWNER_PREFIXES[prefix]


def declared_owner(repo: Path) -> str | None:
    """Resolve identity without using a mutable checkout directory name."""
    return _declared_public_surface(repo) or _declared_owner_prefix(repo)


def canonical_owner(value: object) -> str | None:
    """Canonicalize a legacy owner slug, including renamed first-party repos."""
    if value is None:
        return None
    owner = repository_slug(value)
    return owner or None


def remote_owner(repo: Path) -> str | None:
    """Prefer origin; without it, accept only a sole remote. Never contact it."""
    remotes = git_text(repo, ("remote",)).splitlines()
    remote = "origin" if "origin" in remotes else remotes[0] if len(remotes) == 1 else None
    if remote is None:
        return None
    name = _remote_name(git_text(repo, ("remote", "get-url", remote)).strip())
    return repository_slug(name) if name else None


def repository_owner(repo: Path, legacy_owner: object = None) -> str | None:
    """Resolve remote, declared, then legacy identity in stable order."""
    return remote_owner(repo) or declared_owner(repo) or canonical_owner(legacy_owner)
