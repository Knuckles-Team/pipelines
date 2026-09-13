"""Blank Rust comments and literals while keeping every source offset."""

from __future__ import annotations

import re

RAW_LITERAL_START = re.compile(r'(?:b|c)?r(?P<hashes>#{0,255})"')
CHAR_LITERAL = re.compile(r"b?'(?:\\(?:.|x[0-9A-Fa-f]{2}|u\{[0-9A-Fa-f_]+\})|[^'\\\n])'")
STRING_LITERAL_START = re.compile(r'(?:b|c)?"')


class RustLexError(ValueError):
    """The source cannot be lexed (unterminated comment, literal or block)."""


def _line_comment_end(source: str, start: int) -> int:
    end = source.find("\n", start + 2)
    return len(source) if end < 0 else end


def _block_comment_end(source: str, start: int) -> int:
    """Offset after the nestable ``/*`` comment opening at ``start``."""
    depth, cursor = 1, start + 2
    while cursor < len(source) and depth:
        if source.startswith("/*", cursor):
            depth, cursor = depth + 1, cursor + 2
        elif source.startswith("*/", cursor):
            depth, cursor = depth - 1, cursor + 2
        else:
            cursor += 1
    if depth:
        raise RustLexError("unterminated Rust block comment")
    return cursor


def _raw_string_end(source: str, opener: re.Match[str]) -> int:
    terminator = '"' + opener.group("hashes")
    end = source.find(terminator, opener.end())
    if end < 0:
        raise RustLexError("unterminated Rust raw string")
    return end + len(terminator)


def _quoted_string_end(source: str, quote: int) -> int:
    end = quote + 1
    while end < len(source) and source[end] != '"':
        end += 2 if source[end] == "\\" else 1
    if end >= len(source):
        raise RustLexError("unterminated Rust literal")
    return end + 1


def _literal_span(source: str, index: int) -> int | None:
    raw = RAW_LITERAL_START.match(source, index)
    if raw is not None:
        return _raw_string_end(source, raw)
    character = CHAR_LITERAL.match(source, index)
    if character is not None:
        return character.end()
    quoted = STRING_LITERAL_START.match(source, index)
    if quoted is not None:
        return _quoted_string_end(source, quoted.end() - 1)
    return None


def lexical_span(source: str, index: int) -> tuple[int, bool] | None:
    """``(end, is_literal)`` of a comment or literal opening at ``index``.

    ``None`` when ``index`` opens neither. Byte and C string prefixes belong to
    their literal token.
    """
    if source.startswith("//", index):
        return _line_comment_end(source, index), False
    if source.startswith("/*", index):
        return _block_comment_end(source, index), False
    end = _literal_span(source, index)
    return None if end is None else (end, True)


def code_mask(source: str) -> str:
    """Source with comments and literals blanked, newlines and offsets kept."""
    masked = list(source)
    index = 0
    while index < len(source):
        span = lexical_span(source, index)
        if span is None:
            index += 1
            continue
        end = span[0]
        for position in range(index, end):
            if source[position] != "\n":
                masked[position] = " "
        index = end
    return "".join(masked)
