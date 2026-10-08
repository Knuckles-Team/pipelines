"""In-scope files for the ste gates.

Doc scope: the consumer's ``[tool.pipelines_hooks.ste.paths]`` (default:
the five standard top-level docs plus ``docs/``). Code scope: ``code_paths``
(files whose argparse strings get scanned). ``exempt`` removes entries by
name or by path pattern.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.tracked import tracked_paths
from pipelines_hooks.ste.staleness import StalePattern
from pipelines_hooks.ste.words import DEFAULT_STALENESS

DEFAULT_DOC_PATHS: tuple[str, ...] = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "docs",
)


@dataclass(frozen=True)
class SteConfig:
    """The validated ste scope for one repository."""

    paths: tuple[str, ...]
    exempt: tuple[str, ...]
    code_paths: tuple[str, ...]
    staleness: tuple[StalePattern, ...]


def _staleness(section: Mapping[str, object]) -> tuple[StalePattern, ...]:
    value = section.get("staleness", [])
    if not isinstance(value, list):
        raise CannotRun("[tool.pipelines_hooks.ste.staleness] must be a list of pattern tables")
    patterns: list[StalePattern] = []
    for index, entry in enumerate(value, 1):
        if not isinstance(entry, Mapping):
            raise CannotRun(f"ste staleness entry {index} must be a table")
        pattern = entry.get("pattern")
        message = entry.get("message")
        if not isinstance(pattern, str) or not pattern.strip():
            raise CannotRun(f"ste staleness entry {index} needs a non-empty pattern")
        if not isinstance(message, str) or not message.strip():
            raise CannotRun(f"ste staleness entry {index} needs a non-empty message")
        patterns.append(StalePattern(pattern, message))
    return DEFAULT_STALENESS + tuple(patterns)


def load_ste(root: Path) -> SteConfig:
    """The repository's ste configuration (defaults when the table is absent)."""
    section = load_config(root).section("ste")
    return SteConfig(
        paths=string_tuple(section.get("paths", list(DEFAULT_DOC_PATHS)), "paths"),
        exempt=string_tuple(section.get("exempt", []), "exempt"),
        code_paths=string_tuple(section.get("code_paths", []), "code_paths"),
        staleness=_staleness(section),
    )


def _name(rel: str) -> str:
    return rel.rsplit("/", 1)[-1]


def _excluded(rel: str, exempt: tuple[str, ...]) -> bool:
    name = _name(rel)
    return any(fnmatch(rel, pattern) or fnmatch(name, pattern) for pattern in exempt)


def _entry_matches(rel: str, entry: str) -> bool:
    if entry.endswith(".md") or entry.endswith(".py"):
        if rel == entry:
            return True
        return "/" not in entry and _name(rel) == entry
    return rel.startswith(entry.rstrip("/") + "/")


def in_scope_doc(rel: str, cfg: SteConfig) -> bool:
    """Whether a tracked doc path is inside the ste scope."""
    if _excluded(rel, cfg.exempt):
        return False
    return any(_entry_matches(rel, entry) for entry in cfg.paths)


def in_scope_code(rel: str, cfg: SteConfig) -> bool:
    """Whether a tracked Python path has its CLI strings scanned."""
    if not rel.endswith(".py") or not cfg.code_paths or _excluded(rel, cfg.exempt):
        return False
    return any(_entry_matches(rel, entry) for entry in cfg.code_paths)


def doc_files(root: Path, cfg: SteConfig) -> list[str]:
    """Tracked in-scope doc paths, relative to the repository root."""
    return [rel for rel in tracked_paths(root) if in_scope_doc(rel, cfg)]


def code_files(root: Path, cfg: SteConfig) -> list[str]:
    """Tracked in-scope Python paths, relative to the repository root."""
    return [rel for rel in tracked_paths(root) if in_scope_code(rel, cfg)]
