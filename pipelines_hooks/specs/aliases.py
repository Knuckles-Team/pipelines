"""Requirement-ID prefix aliases: ``.config/spec-aliases.toml`` (reference/spec-standard.md).

A repository that renames an ID prefix (``GRAPHOS-`` to ``ARBORA-``) cannot
rewrite the ``Spec:`` trailers already in its history. The alias file maps each
retired prefix to its canonical replacement, one top-level string entry each::

    "GRAPHOS-" = "ARBORA-"

A single renumbered row maps by its exact old ID, for example a pre-standard
``DS-01`` that became ``WEBUI-DESIGN-R012``::

    "DS-01" = "WEBUI-DESIGN-R012"

An already standardized retired ID can also map to one active current row::

    "FOO-R002.2.2.3.1" = "FOO-R002.2.3.1"

Standard-ID alias sources must have no current row, including retired rows.
An exact alias key may start with a retired prefix: the exact alias applies first and
the prefix mapping is not applied to its result (one hop). Aliases must not target
absent or retired rows, or chain through another alias or a retired prefix. Exact
aliases never implicitly map children. Trailer checks still require the target to be bound.

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
from pipelines_hooks.specs.requirements_doc import parse_rows
from pipelines_hooks.specs.trailer_ids import named_ids

ALIAS_FILE = ".config/spec-aliases.toml"
_PREFIX_RE = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-")
_OLD_ID_RE = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[0-9]+(?:\.[0-9]+)*")
_NEW_ID_RE = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R[0-9]{3}(?:\.[0-9]+)*")

Aliases = Mapping[str, str]


def _validated(document: dict, path: Path) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for old, new in document.items():
        if not isinstance(new, str):
            raise CannotRun(f"{path}: alias {old!r} must map to a string prefix")
        if _PREFIX_RE.fullmatch(old):
            if not _PREFIX_RE.fullmatch(new):
                raise CannotRun(f"{path}: {new!r} is not an ID prefix (upper-case, ending in '-')")
        elif not ((_OLD_ID_RE.fullmatch(old) or _NEW_ID_RE.fullmatch(old)) and _NEW_ID_RE.fullmatch(new)):
            raise CannotRun(
                f"{path}: {old!r} must be an ID prefix ending in '-' or an exact old row ID mapped to a standard ID"
            )
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
    aliases = _validated(document, path)
    _validate_standard_aliases(root, aliases, path)
    return aliases


def _validate_standard_aliases(root: Path, aliases: Aliases, path: Path) -> None:
    """A standardized alias retires an exact identity, not a live row or prefix."""
    standard = {old: new for old, new in aliases.items() if _NEW_ID_RE.fullmatch(old)}
    if not standard:
        return
    current: set[str] = set()
    active: set[str] = set()
    for requirements in sorted(root.glob("specs/*/requirements.md")):
        try:
            rows = parse_rows(requirements.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise CannotRun(f"{path}: could not read {requirements}: {exc}") from exc
        current.update(row.id for row in rows)
        active.update(row.id for row in rows if row.retired_reason is None)
    validate_alias_inventory(aliases, current, active, path)


def validate_alias_inventory(aliases: Aliases, current: set[str], active: set[str], path: Path) -> None:
    """Validate standard aliases against a complete frozen requirement inventory."""
    standard = {old: new for old, new in aliases.items() if _NEW_ID_RE.fullmatch(old)}
    for old, new in standard.items():
        if retired_prefix(new, aliases):
            raise CannotRun(
                f"{path}: standard alias {old!r} target {new!r} starts with a retired prefix or is an alias key"
            )
        if old in current:
            raise CannotRun(f"{path}: standard alias {old!r} still has a requirement row; remove the old row")
        if new not in active:
            raise CannotRun(f"{path}: standard alias {old!r} target {new!r} is not an active requirement row")


def validate_alias_document(
    document: dict, *, current_ids: set[str], active_ids: set[str], source_path: Path
) -> dict[str, str]:
    """Validate raw frozen alias TOML using the same rules as filesystem gates."""
    aliases = _validated(document, source_path)
    validate_alias_inventory(aliases, current_ids, active_ids, source_path)
    return aliases


def retired_prefix(rid: str, aliases: Aliases) -> str | None:
    """The exact retired ID ``rid``, else the longest retired prefix it starts with, or ``None``."""
    if rid in aliases:
        return rid
    matches = [old for old in aliases if old.endswith("-") and rid.startswith(old)]
    return max(matches, key=len) if matches else None


def canonical_id(rid: str, aliases: Aliases) -> str:
    """``rid`` with a retired prefix replaced by its canonical one."""
    old = retired_prefix(rid, aliases)
    if old is None:
        return rid
    return aliases[old] if old == rid else aliases[old] + rid[len(old) :]


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
