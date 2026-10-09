"""Requirement-ID parsing for ``Spec:`` trailers: ranges, shorthand and the ``none`` exemption."""

from __future__ import annotations

import re
from collections.abc import Iterable

TRAILER_JOIN = "\x1f"
NONE_EXEMPTION = re.compile(r"(?i)^none\b")
_RANGE = re.compile(
    r"^(?P<base>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-)R(?P<start>\d{2,3})\.\.R?(?P<end>\d{2,3})$"
)
_PREFIX = re.compile(r"^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-)R\d")
_BARE = re.compile(r"^R\d{2,3}(?:\.\d+)*(?:\.\.R?\d{2,3})?$")


def _expand_token(token: str) -> list[str]:
    """A ``PREFIX-R001..R005`` range expands to its member IDs; anything else is itself."""
    match = _RANGE.match(token)
    if not match:
        return [token]
    width = len(match.group("start"))
    start, end = int(match.group("start")), int(match.group("end"))
    return [
        f"{match.group('base')}R{number:0{width}d}" for number in range(start, end + 1)
    ]


def _trailer_tokens(trailer_raw: str) -> list[str]:
    tokens = (
        part.strip()
        for group in trailer_raw.split(TRAILER_JOIN)
        for part in group.split(",")
    )
    return [token for token in tokens if token]


def _qualified(tokens: list[str]) -> list[str]:
    """``X-R001.1, R001.2``: a bare ``R###`` token inherits the preceding token's prefix."""
    prefix, out = "", []
    for token in tokens:
        match = _PREFIX.match(token)
        if match:
            prefix = match.group(1)
        elif prefix and _BARE.match(token):
            token = prefix + token
        out.append(token)
    return out


def named_ids(trailers: Iterable[str]) -> list[str]:
    """Every requirement ID any commit's ``Spec:`` trailer names, ranges and shorthand expanded."""
    ids: list[str] = []
    for trailer_raw in trailers:
        tokens = [
            t for t in _trailer_tokens(trailer_raw) if not NONE_EXEMPTION.match(t)
        ]
        for token in _qualified(tokens):
            ids.extend(_expand_token(token))
    return ids
