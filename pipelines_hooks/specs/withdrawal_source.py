"""Conservative Rust comment-only changes for acceptance-evidence withdrawal."""

from __future__ import annotations

import re

_RAW = re.compile(r'(?:br|cr|r)(#{0,255})"')
_LIFETIME = re.compile(r"'[A-Za-z_][A-Za-z_0-9]*")


def _quoted_end(source: str, start: int, quote: str) -> int:
    """Return the first unescaped closing quote, or reject an unfinished token."""
    cursor = start + 1
    while cursor < len(source):
        if source[cursor] == "\\":
            cursor += 2
        elif source[cursor] == quote:
            return cursor + 1
        else:
            cursor += 1
    raise ValueError("unterminated quoted token")


def _block_end(source: str, start: int) -> int:
    """Rust block comments nest; quote-like text within them has no significance."""
    cursor, depth = start + 2, 1
    while cursor < len(source):
        if source.startswith("/*", cursor):
            depth += 1
            cursor += 2
        elif source.startswith("*/", cursor):
            depth -= 1
            cursor += 2
            if not depth:
                return cursor
        else:
            cursor += 1
    raise ValueError("unterminated block comment")


def _token_end(source: str, cursor: int) -> int:
    """Skip literal and block tokens, retaining their original bytes."""
    raw = _RAW.match(source, cursor)
    if raw:
        delimiter = '"' + raw.group(1)
        end = source.find(delimiter, raw.end())
        if end < 0:
            raise ValueError("unterminated raw string")
        return end + len(delimiter)
    if source.startswith("/*", cursor):
        return _block_end(source, cursor)
    if source[cursor] == '"':
        return _quoted_end(source, cursor, '"')
    if source[cursor] == "'":
        lifetime = _LIFETIME.match(source, cursor)
        if lifetime and source[lifetime.end() : lifetime.end() + 1] != "'":
            return lifetime.end()
        return _quoted_end(source, cursor, "'")
    return cursor + 1


def _without_withdrawal_comments(source: str, ids: set[str]) -> str:
    allowed = {f"// spec: {identifier}" for identifier in ids}
    allowed.update(
        f"// Partial refusal coverage for {identifier}; "
        "successful-operation acceptance remains open."
        for identifier in ids
    )
    chunks: list[str] = []
    cursor = retained = 0
    while cursor < len(source):
        if not source.startswith("//", cursor):
            cursor = _token_end(source, cursor)
            continue
        end = source.find("\n", cursor)
        end = len(source) if end < 0 else end + 1
        start = source.rfind("\n", 0, cursor) + 1
        prefix = source[start:cursor]
        comment = source[cursor:end].removesuffix("\n").removesuffix("\r")
        if not prefix.strip(" \t") and comment in allowed:
            chunks.append(source[retained:start])
            retained = end
        cursor = end
    chunks.append(source[retained:])
    return "".join(chunks)


def source_withdrawal_only(before: str, after: str, ids: set[str]) -> bool:
    """Allow only declared standalone Rust marker removal or canonical replacement.

    The caller must restrict paths to Rust files, reject mode changes, and prove
    each declared ID was bound before and has no remaining binding afterward.
    Literal contents, executable code, and all other comments remain identical.
    """
    try:
        return _without_withdrawal_comments(
            before, ids
        ) == _without_withdrawal_comments(after, ids)
    except ValueError:
        return False
