"""Stream tracked paths and bodies for prohibited identities without loading whole files.

Text is split into Unicode lexical groups (letters, numbers, marks, ``_`` and
``-``). A group matches when an identity appears in it with separators removed
and the match has non-word boundaries, unless it is formed only by the
interiors of adjacent camel-case segments. Exact and explicitly delimited
identities therefore remain sensitive while longer product words do not match.
"""

from __future__ import annotations

import codecs
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


READ_SIZE = 64 * 1024
MAX_GROUP_BYTES = 64 * 1024
# A longer run (an embedded base64 blob) is scanned in windows that overlap by this much,
# so an identity that straddles a window edge is still seen whole.
GROUP_OVERLAP_BYTES = 4 * 1024
_CAMEL_SEGMENT_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_SEPARATORS = frozenset("_-")


@dataclass(frozen=True, slots=True)
class IdentityFinding:
    path: str
    line: int
    evidence: str


def _is_word_character(value: str) -> bool:
    """Whether ``value`` extends an identity-bearing Unicode word."""
    return value.isalnum() or unicodedata.category(value).startswith("M")


def _is_group_character(value: str) -> bool:
    return _is_word_character(value) or value in _SEPARATORS


def _ascii_lower(value: str) -> str:
    """Fold ASCII case without expanding Unicode characters or positions."""
    return "".join(chr(ord(character) + 32) if "A" <= character <= "Z" else character for character in value)


def _cross_segment_coincidence(group: str, start: int, end: int) -> bool:
    overlapping = [m.span() for m in _CAMEL_SEGMENT_RE.finditer(group) if m.start() < end and m.end() > start]
    return len(overlapping) >= 2 and start > overlapping[0][0] and end < overlapping[-1][1]


def group_matches(group: bytes, identities: tuple[bytes, ...]) -> bool:
    text = group.decode("utf-8", "replace")
    positions = [index for index, value in enumerate(text) if value not in _SEPARATORS]
    normalized = _ascii_lower("".join(text[index] for index in positions))
    for encoded_identity in identities:
        try:
            identity = encoded_identity.decode("ascii").lower()
        except UnicodeDecodeError:
            continue
        if not identity:
            continue
        start = normalized.find(identity)
        while start >= 0:
            raw_start, raw_end = positions[start], positions[start + len(identity) - 1] + 1
            bounded = (raw_start == 0 or not _is_word_character(text[raw_start - 1])) and (
                raw_end == len(text) or not _is_word_character(text[raw_end])
            )
            if bounded and not _cross_segment_coincidence(text, raw_start, raw_end):
                return True
            start = normalized.find(identity, start + 1)
    return False


@dataclass
class _Grouper:
    """Accumulates lexical groups across chunk boundaries."""

    group: bytearray
    line: int = 1
    group_line: int = 1

    def feed(self, value: str) -> tuple[int, bytes] | None:
        """Consume one character; return a completed group at a delimiter."""
        if _is_group_character(value):
            self.group_line = self.group_line if self.group else self.line
            encoded = value.encode("utf-8")
            window = None
            if len(self.group) + len(encoded) >= MAX_GROUP_BYTES:
                window = (self.group_line, bytes(self.group))
                del self.group[:-GROUP_OVERLAP_BYTES]
            self.group.extend(encoded)
            return window
        completed = self.flush()
        self.line += value == "\n"
        return completed

    def flush(self) -> tuple[int, bytes] | None:
        if not self.group:
            return None
        completed = (self.group_line, bytes(self.group))
        self.group.clear()
        return completed


def _groups(stream: BinaryIO) -> Iterator[tuple[int, bytes]]:
    """``(line, group)`` for every lexical group, streamed in bounded chunks."""
    grouper = _Grouper(bytearray())
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    while chunk := stream.read(READ_SIZE):
        for value in decoder.decode(chunk):
            completed = grouper.feed(value)
            if completed is not None:
                yield completed
    for value in decoder.decode(b"", final=True):
        completed = grouper.feed(value)
        if completed is not None:
            yield completed
    last = grouper.flush()
    if last:
        yield last


def scan_prohibited_identities(
    root: Path, paths: Iterable[Path], identities: tuple[bytes, ...]
) -> list[IdentityFinding]:
    """Every tracked path name and body occurrence of a prohibited identity."""
    findings: list[IdentityFinding] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if group_matches(relative.encode(), identities):
            findings.append(IdentityFinding(relative, 0, relative))
        with path.open("rb") as stream:
            findings.extend(
                IdentityFinding(relative, line, group.decode("utf-8", "replace"))
                for line, group in _groups(stream)
                if group_matches(group, identities)
            )
    return findings
