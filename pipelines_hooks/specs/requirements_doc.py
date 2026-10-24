"""Parsing the requirement rows of a ``specs/<id>/requirements.md`` table."""

from __future__ import annotations

import re
from typing import NamedTuple

from pipelines_hooks.specs.ids import ID, ROW_RE

_TITLE_RE = re.compile(r"\*\*(.+?)\*\*")
_RETIRED_RE = re.compile(r"RETIRED:?\s*(.*)")
_DEPENDS_RE = re.compile(rf"\bDepends-on:\s*({ID}(?:\s*,\s*{ID})*)")


class Row(NamedTuple):
    """One requirement row: its ID, title, and retirement reason if retired."""

    id: str
    title: str
    retired_reason: str | None
    depends_on: tuple[str, ...] = ()


def _row_title(body: str) -> str:
    match = _TITLE_RE.search(body)
    raw = match.group(1) if match else body.split("|")[0]
    return raw.strip().rstrip(".")


def _retired_reason(title: str) -> str | None:
    match = _RETIRED_RE.match(title)
    if not match:
        return None
    return match.group(1).strip() or "retired"


def _ordered_unique(found: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(found))


def _declared(pattern: re.Pattern[str], body: str, item: str) -> tuple[str, ...]:
    """The comma-separated IDs of every ``Depends-on:`` declaration in a row."""
    found: list[str] = []
    for match in pattern.finditer(body):
        found += re.findall(item, match.group(1))
    return _ordered_unique(found)


def parse_rows(text: str) -> list[Row]:
    """Every distinct requirement row, in document order (first occurrence wins)."""
    seen: set[str] = set()
    rows: list[Row] = []
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        title = _row_title(match.group(2))
        body = match.group(2)
        rows.append(
            Row(
                match.group(1),
                title,
                _retired_reason(title),
                _declared(_DEPENDS_RE, body, ID),
            )
        )
    return rows
