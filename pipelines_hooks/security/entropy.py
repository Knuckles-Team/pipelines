"""The keyword-free high-entropy sweep (informational only, never blocking).

A candidate must survive three filters -- a known-noise classifier, three
distinct character classes, and an entropy floor. Any one alone is mostly
hashes. Hard-failing on entropy alone would need a bespoke exemption list, so
the sweep stays a human-reviewed signal.
"""

from __future__ import annotations

import math
import re

TOKEN_RE = re.compile(r"[A-Za-z0-9+/_.=-]{24,64}")
MIN_ENTROPY = 4.4
LOCKFILE_SUFFIXES = (".lock", "-lock.json", "uv.lock", "poetry.lock", "Cargo.lock")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: A dotted identifier path (a docstring cross-reference) is not key material
#: when every segment READS like source: snake_case, CONSTANT or CamelCase. The
#: segment shapes are load-bearing -- a JWT is also dotted and alphanumeric.
_SEGMENT_SHAPES = (
    re.compile(r"^[a-z_][a-z0-9_]*$"),
    re.compile(r"^[A-Z_][A-Z0-9_]*$"),
    re.compile(r"^[A-Z][a-z0-9]*(?:[A-Z][a-z0-9]*)*$"),
)
_CHARACTER_CLASSES = (r"[a-z]", r"[A-Z]", r"[0-9]", r"[+/_.=-]")


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    return -sum((c / len(value)) * math.log2(c / len(value)) for c in counts.values())


def _is_dotted_identifier_path(token: str) -> bool:
    segments = token.split(".")
    return len(segments) >= 2 and all(any(shape.match(s) for shape in _SEGMENT_SHAPES) for s in segments)


def is_noise(token: str) -> bool:
    """Hashes, UUIDs, identifiers and dotted identifier paths are never secrets."""
    return bool(
        _HEX_RE.match(token) or _UUID_RE.match(token) or _IDENTIFIER_RE.match(token) or _is_dotted_identifier_path(token)
    )


def high_entropy_tokens(content: str) -> list[tuple[str, float]]:
    """Tokens in one added line that look like random credential material."""
    found = []
    for match in TOKEN_RE.finditer(content):
        token = match.group(0)
        if is_noise(token) or sum(bool(re.search(p, token)) for p in _CHARACTER_CLASSES) < 3:
            continue
        entropy = shannon_entropy(token)
        if entropy >= MIN_ENTROPY:
            found.append((token, entropy))
    return found


def is_lockfile(path: str) -> bool:
    return path != "?" and path.endswith(LOCKFILE_SUFFIXES)
