"""Discover URLs that become visible only after scalar percent decoding."""

from __future__ import annotations

import re
from urllib.parse import unquote

from .constants import BEARER_PATTERN, SECRET_PATTERN, URL_PATTERN
from .errors import _fail
from .url_security import _scan_url


_VALID_PERCENT_PATTERN = re.compile(r"%[0-9A-Fa-f]{2}")
_ENCODED_URL_PATTERN = re.compile(
    r"(?:h|%(?:25)*68)(?:t|%(?:25)*74){2}(?:p|%(?:25)*70)"
    r"(?:s|%(?:25)*73)?(?::|%(?:25)*3a)"
    r"(?:/|%(?:25)*2f){2}",
    re.IGNORECASE,
)
_MAX_DECODE_PASSES = 3


def _decode_scalar_pass(raw: str, label: str) -> str | None:
    """Decode one scalar layer, reserving URL errors for URL-shaped text."""

    try:
        return unquote(raw, errors="strict")
    except UnicodeDecodeError:
        if _ENCODED_URL_PATTERN.search(raw):
            _fail(f"{label}-url-invalid")
        return None


def _should_decode(value: str) -> bool:
    return bool(_VALID_PERCENT_PATTERN.search(value)) and not URL_PATTERN.search(value)


def _canonical_scalar(raw: str, label: str) -> str:
    """Decode a scalar for URL discovery without rejecting ordinary percent text."""

    current = raw
    for _ in range(_MAX_DECODE_PASSES):
        if not _should_decode(current):
            return current
        decoded = _decode_scalar_pass(current, label)
        if decoded is None:
            return raw
        current = decoded
    _reject_decode_bound(current, label)
    return current


def _has_decoded_secret(value: str) -> bool:
    return any(
        pattern.search(value)
        for pattern in (SECRET_PATTERN, BEARER_PATTERN)
    )


def _reject_decoded_secrets(value: str, label: str) -> None:
    """Reject secrets revealed in canonical scalar text without recursing."""

    if _has_decoded_secret(value):
        _fail(f"{label}-secret-like-value")


def _reject_decode_bound(current: str, label: str) -> None:
    """Fail if one more pass would expose security-relevant structure."""

    probe = _decode_scalar_pass(current, label)
    if probe is not None:
        _reject_decoded_secrets(probe, label)
    if _ENCODED_URL_PATTERN.search(current) or (
        probe is not None and URL_PATTERN.search(probe)
    ):
        _fail(f"{label}-url-invalid")


def _scan_urls(raw: str, label: str) -> None:
    """Scan raw URLs and canonicalize only the text outside their spans."""

    matches = tuple(URL_PATTERN.finditer(raw))
    segments: list[str] = []
    cursor = 0
    for match in matches:
        segments.append(raw[cursor : match.start()])
        cursor = match.end()
        _scan_url(match.group(0).rstrip(".,;:"), label)
    segments.append(raw[cursor:])
    for segment in segments:
        canonical = _canonical_scalar(segment, label)
        _reject_decoded_secrets(canonical, label)
        for match in URL_PATTERN.finditer(canonical):
            _scan_url(match.group(0).rstrip(".,;:"), label)
