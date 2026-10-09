"""Parsing the requirement rows of a ``specs/<id>/requirements.md`` table."""

from __future__ import annotations

import re
from typing import NamedTuple

from pipelines_hooks.specs.ids import ROW_RE

_TITLE_RE = re.compile(r"\*\*(.+?)\*\*")
_RETIRED_RE = re.compile(r"RETIRED:?\s*(.*)")


class Row(NamedTuple):
    """One requirement row: its ID, title, and retirement reason if retired."""

    id: str
    title: str
    retired_reason: str | None


def _row_title(body: str) -> str:
    match = _TITLE_RE.search(body)
    raw = match.group(1) if match else body.split("|")[0]
    return raw.strip().rstrip(".")


def _retired_reason(title: str) -> str | None:
    match = _RETIRED_RE.match(title)
    if not match:
        return None
    return match.group(1).strip() or "retired"


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
        rows.append(Row(match.group(1), title, _retired_reason(title)))
    return rows
