"""Parsing the requirement rows of a ``specs/<id>/requirements.md`` table."""

from __future__ import annotations

import re
from typing import NamedTuple

from pipelines_hooks.specs.ids import ID, ROW_RE

_TITLE_RE = re.compile(r"\*\*(.+?)\*\*")
_RETIRED_RE = re.compile(r"RETIRED:?\s*(.*)")
_RELATIVE = r"R\d{2,3}(?:\.\d+)*|\.\d+(?:\.\d+)*"
#: "Depends on" and "Depends-on:" take backticked or bare full IDs. "Requires" and "After" take backticked IDs only.
_DEPENDS_RE = re.compile(r"\b(?:[Dd]epends[ -]on:?)\s*(?P<run>[^|]*?)(?:\.(?=\s|\||$)|\||$)")
_NEEDS_RE = re.compile(r"\b(?:Requires|After)\s+(?P<run>`[^|]*?)(?:\.(?=\s|\||$)|\||$)")
_TICKED_RE = re.compile(r"`([^`]+)`")


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


def _resolve(token: str, row_id: str) -> str | None:
    """A full ID stays; ``R001.1`` takes the row's spec prefix; ``.1`` is a child of the row's parent."""
    token = token.strip()
    if re.fullmatch(ID, token):
        return token
    if re.fullmatch(_RELATIVE, token):
        if token.startswith("."):
            base = row_id.rsplit(".", 1)[0] if re.search(r"R\d{2,3}\.\d+(?:\.\d+)*$", row_id) else row_id
            return base + token
        return row_id.rsplit("-R", 1)[0] + "-" + token
    return None


def _declared_ids(body: str, row_id: str) -> tuple[str, ...]:
    """Prerequisite IDs named by ``Depends on``, ``Depends-on:``, ``Requires`` or ``After`` in one row."""
    found: list[str] = []
    for pattern, bare in ((_DEPENDS_RE, True), (_NEEDS_RE, False)):
        for match in pattern.finditer(body):
            run = match.group("run")
            tokens = _TICKED_RE.findall(run)
            if bare:
                tokens += re.findall(rf"(?<![`\w-])({ID})(?![\w`])", _TICKED_RE.sub(" ", run))
            found += [t for t in (_resolve(t, row_id) for t in tokens) if t]
    return tuple(dict.fromkeys(i for i in found if i != row_id))


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
                _declared_ids(body, match.group(1)),
            )
        )
    return rows
