"""Content-addressed identity of a jscpd clone pair.

A pair is keyed by its format, the fragment digest, its two paths and its
ordinal among the pairs sharing those three. Line numbers are never part of the
key: a line shift elsewhere in either file (or before/after living in different
snapshot directories) does not read as a NEW pair. The ordinal still separates
repeated occurrences, so a third copy of a block inside one file, or a second
copied block between the same two files, is NEW.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.paths import relative_to_root

_LOCATION_SUFFIX = re.compile(r":(?P<format>[A-Za-z0-9_-]+)(?::(?P<start>[0-9]+)-(?P<end>[0-9]+))?$")
Span = tuple[str, int, int]
PairKey = tuple[str, str, tuple[str, str], int]
Pairs = dict[PairKey, tuple[Span, Span]]


def report_file_path(name: str, format_name: str) -> str:
    """Strip jscpd's virtual-format ``:<format>[:<start>-<end>]`` location suffix."""
    match = _LOCATION_SUFFIX.search(name)
    return name[: match.start()] if match and match.group("format") == format_name else name


def relative_report_path(name: str, root: Path) -> str:
    """A trusted snapshot-relative report path, or :class:`CannotRun`."""
    try:
        relative = relative_to_root(name, root)
    except ValueError as exc:
        raise CannotRun(f"jscpd report path escapes the scan root: {exc}") from exc
    if not relative:
        raise CannotRun(f"jscpd report path names the scan root: {name!r}")
    return relative


def _span(side: dict[str, Any], format_name: str, root: Path) -> Span:
    path = relative_report_path(report_file_path(side["name"], format_name), root)
    return path, side["startLoc"]["line"], side["endLoc"]["line"]


def clone_spans(clone: dict[str, Any], root: Path) -> tuple[str, str, tuple[Span, Span]]:
    """``(format, fragment digest, sorted spans)`` for one validated clone."""
    format_name = clone["format"]
    first, second = sorted((_span(clone["firstFile"], format_name, root), _span(clone["secondFile"], format_name, root)))
    digest = hashlib.sha256(clone["fragment"].encode("utf-8", "surrogatepass")).hexdigest()
    return format_name, digest, (first, second)


def keys(document: dict[str, Any], root: Path) -> Pairs:
    """Every pair of a validated report, keyed position-independently."""
    pairs: Pairs = {}
    ordinals: dict[tuple[str, str, tuple[str, str]], int] = {}
    for format_name, digest, spans in sorted(clone_spans(clone, root) for clone in document["duplicates"]):
        identity = (format_name, digest, (spans[0][0], spans[1][0]))
        ordinals[identity] = ordinals.get(identity, -1) + 1
        pairs[(*identity, ordinals[identity])] = spans
    return pairs


def render_pair(key: PairKey, spans: tuple[Span, Span]) -> str:
    """``[format] path:start-end <-> path:start-end``."""
    first, second = (f"{path}:{start}-{end}" for path, start, end in spans)
    return f"[{key[0]}] {first} <-> {second}"
