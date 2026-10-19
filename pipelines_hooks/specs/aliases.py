"""Requirement-ID prefix aliases: ``.config/spec-aliases.toml`` (reference/spec-standard.md).

A repository that renames an ID prefix (``GRAPHOS-`` to ``ARBORA-``) cannot
rewrite the ``Spec:`` trailers already in its history. The alias file maps each
retired prefix to its canonical replacement, one top-level string entry each::

    "GRAPHOS-" = "ARBORA-"

Every spec gate reads IDs through :func:`canonical_id`, so a historical trailer
or test binding that uses the old prefix counts for the canonical (new) ID. The
canonical ID is always the new one: requirements.md rows and status.json carry
it. New commits should use the new prefix; ``spec-trailers`` warns (never fails)
when one does not. A missing file means no aliases.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.specs.trailer_ids import named_ids

ALIAS_FILE = ".config/spec-aliases.toml"
_PREFIX_RE = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-")

Aliases = Mapping[str, str]


def _validated(document: dict, path: Path) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for old, new in document.items():
        if not isinstance(new, str):
            raise CannotRun(f"{path}: alias {old!r} must map to a string prefix")
        for prefix in (old, new):
            if not _PREFIX_RE.fullmatch(prefix):
                raise CannotRun(f"{path}: {prefix!r} is not an ID prefix (upper-case, ending in '-')")
        if old == new:
            raise CannotRun(f"{path}: alias {old!r} maps to itself")
        aliases[old] = new
    chained = sorted(set(aliases) & set(aliases.values()))
    if chained:
        raise CannotRun(f"{path}: chained aliases are not allowed: {', '.join(chained)}")
    return aliases


def load_aliases(root: Path) -> dict[str, str]:
    """Retired prefix -> canonical prefix, from ``root/.config/spec-aliases.toml``."""
    path = root / ALIAS_FILE
    if not path.is_file():
        return {}
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"{path}: unreadable spec alias file ({exc})") from exc
    return _validated(document, path)


def retired_prefix(rid: str, aliases: Aliases) -> str | None:
    """The longest retired prefix ``rid`` starts with, or ``None``."""
    matches = [old for old in aliases if rid.startswith(old)]
    return max(matches, key=len) if matches else None


def canonical_id(rid: str, aliases: Aliases) -> str:
    """``rid`` with a retired prefix replaced by its canonical one."""
    old = retired_prefix(rid, aliases)
    return aliases[old] + rid[len(old) :] if old else rid


def canonical_ids(ids: Iterable[str], aliases: Aliases) -> list[str]:
    """Every ID in ``ids`` canonicalized, order kept."""
    return [canonical_id(rid, aliases) for rid in ids]


def canonical_sets(by_id: Mapping[str, set[str]], aliases: Aliases) -> dict[str, set[str]]:
    """An ``ID -> set`` map re-keyed by canonical ID; old and new evidence are merged."""
    out: dict[str, set[str]] = {}
    for rid, values in by_id.items():
        out.setdefault(canonical_id(rid, aliases), set()).update(values)
    return out


def canonical_lists(by_id: Mapping[str, list[str]], aliases: Aliases) -> dict[str, list[str]]:
    """An ``ID -> list`` map re-keyed by canonical ID; old and new evidence are merged."""
    out: dict[str, list[str]] = {}
    for rid, values in by_id.items():
        out.setdefault(canonical_id(rid, aliases), []).extend(values)
    return out


def retired_prefix_warnings(named: Iterable[str], aliases: Aliases) -> list[str]:
    """New commits should name the canonical ID; a retired prefix still counts, so warn only."""
    retired = sorted({rid for rid in named if retired_prefix(rid, aliases)})
    return [
        f"spec-trailers: WARN: retired ID prefix in a new trailer, use {canonical_id(rid, aliases)} "
        f"instead of {rid} (see {ALIAS_FILE})"
        for rid in retired
    ]


def canonical_trailer_ids(trailers: Iterable[str], aliases: Aliases) -> list[str]:
    """Trailer IDs with retired prefixes canonicalized; each retired use prints a WARN."""
    raw_named = named_ids(trailers)
    for warning in retired_prefix_warnings(raw_named, aliases):
        print(warning)
    return canonical_ids(raw_named, aliases)
