"""Stream tracked paths and bodies for prohibited identities without loading whole files.

Text is split into lexical groups (letters, digits, ``_`` and ``-``). A group
matches when an identity appears in it with separators removed, unless the
match is formed only by the interiors of adjacent camel-case segments.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from pipelines_hooks.privacy.identity_catalog import IdentityPolicyError

READ_SIZE = 64 * 1024
MAX_GROUP_BYTES = 64 * 1024
_CAMEL_SEGMENT_RE = re.compile(rb"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_SEPARATORS = frozenset(b"_-")


@dataclass(frozen=True, slots=True)
class IdentityFinding:
    path: str
    line: int
    evidence: str


def _is_group_byte(value: int) -> bool:
    return 48 <= value <= 57 or 65 <= value <= 90 or 97 <= value <= 122 or value in _SEPARATORS


def _cross_segment_coincidence(group: bytes, start: int, end: int) -> bool:
    overlapping = [m.span() for m in _CAMEL_SEGMENT_RE.finditer(group) if m.start() < end and m.end() > start]
    return len(overlapping) >= 2 and start > overlapping[0][0] and end < overlapping[-1][1]


def group_matches(group: bytes, identities: tuple[bytes, ...]) -> bool:
    positions = [index for index, value in enumerate(group) if value not in _SEPARATORS]
    normalized = bytes(group[index] for index in positions).lower()
    for identity in identities:
        start = normalized.find(identity)
        while start >= 0:
            raw_start, raw_end = positions[start], positions[start + len(identity) - 1] + 1
            if not _cross_segment_coincidence(group, raw_start, raw_end):
                return True
            start = normalized.find(identity, start + 1)
    return False


@dataclass
class _Grouper:
    """Accumulates lexical groups across chunk boundaries."""

    group: bytearray
    line: int = 1
    group_line: int = 1

    def feed(self, value: int) -> tuple[int, bytes] | None:
        """Consume one byte; returns a completed group, if this byte ended one."""
        if _is_group_byte(value):
            self.group_line = self.group_line if self.group else self.line
            if len(self.group) >= MAX_GROUP_BYTES:
                raise IdentityPolicyError("tracked lexical group exceeds the size limit")
            self.group.append(value)
            return None
        completed = self.flush()
        self.line += value == 10
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
    while chunk := stream.read(READ_SIZE):
        yield from filter(None, map(grouper.feed, chunk))
    last = grouper.flush()
    if last:
        yield last


def scan_prohibited_identities(root: Path, paths: Iterable[Path], identities: tuple[bytes, ...]) -> list[IdentityFinding]:
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
