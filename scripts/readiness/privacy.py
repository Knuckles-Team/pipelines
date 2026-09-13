"""Reject private endpoints and secret-like values in readiness metadata."""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import SplitResult, unquote, urlsplit

from .constants import BEARER_PATTERN, SECRET_PATTERN, URL_PATTERN
from .errors import _fail
from .ip_addresses import _private_address


_INVALID_PERCENT_PATTERN = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _strict_unquote(raw: str, label: str) -> str:
    """Decode valid UTF-8 percent escapes and reject malformed encodings."""

    if _INVALID_PERCENT_PATTERN.search(raw):
        _fail(f"{label}-url-invalid")
    try:
        return unquote(raw, errors="strict")
    except UnicodeDecodeError:
        _fail(f"{label}-url-invalid")


def _private_hostname(host: str) -> bool:
    return host in {"localhost", "local", "internal"} or host.endswith(
        (".local", ".localhost", ".internal", ".home", ".arpa")
    )


def _reject_private_host(host: str, label: str) -> None:
    """Reject local names and non-public IP address literals."""

    decoded = _strict_unquote(host, label).rstrip(".").lower()
    if _private_hostname(decoded) or _private_address(decoded):
        _fail(f"{label}-private-url")


def _invalid_authority(authority: str) -> bool:
    return any(
        character.isspace() or character in "/?#\\" for character in authority
    )


def _decoded_authority(parsed: SplitResult, label: str) -> str:
    """Validate decoded authority syntax and return its normalized host."""

    authority = _strict_unquote(parsed.netloc, label)
    if _invalid_authority(authority):
        _fail(f"{label}-url-invalid")
    try:
        decoded = urlsplit(f"//{authority}")
        host = decoded.hostname.rstrip(".").lower() if decoded.hostname else ""
        decoded.port
    except ValueError:
        _fail(f"{label}-url-invalid")
    if not host:
        _fail(f"{label}-url-invalid")
    if parsed.username or parsed.password or decoded.username or decoded.password:
        _fail(f"{label}-credential-url")
    return host


def _scan_url(raw: str, label: str) -> None:
    """Validate credentials, query secrets, and private hosts in one URL."""

    try:
        parsed = urlsplit(raw)
    except ValueError:
        _fail(f"{label}-url-invalid")
    host = _decoded_authority(parsed, label)
    _strict_unquote(parsed.path, label)
    query = _strict_unquote(parsed.query, label)
    _strict_unquote(parsed.fragment, label)
    if query and re.search(
        r"(?i)(?:token|secret|password|api[_-]?key|credential|auth)=",
        query,
    ):
        _fail(f"{label}-credential-url")
    _reject_private_host(host, label)


def _scan_text(value: str, label: str) -> None:
    if SECRET_PATTERN.search(value) or BEARER_PATTERN.search(value):
        _fail(f"{label}-secret-like-value")
    for match in URL_PATTERN.finditer(value):
        _scan_url(match.group(0).rstrip(".,;:"), label)


def _scan_children(value: Mapping[object, object] | list[object], label: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                _fail(f"{label}-metadata-invalid")
            _scan_key_values(key, child, label)
            _scan_safe_text(child, label)
        return
    for child in value:
        _scan_safe_text(child, label)


def _scan_key_values(key: str, value: object, label: str) -> None:
    """Scan scalar descendants together with their decoded metadata key."""

    if isinstance(value, list):
        for child in value:
            _scan_key_values(key, child, label)
        return
    if isinstance(value, Mapping):
        return
    if value is None or isinstance(value, (str, bool, int, float)):
        _scan_text(f"{key}={value}", label)


def _scan_safe_text(value: object, label: str) -> None:
    """Recursively reject secrets, credentials, and private URLs."""

    if isinstance(value, str):
        _scan_text(value, label)
    elif isinstance(value, (Mapping, list)):
        _scan_children(value, label)
    elif value is not None and not isinstance(value, (bool, int, float)):
        _fail(f"{label}-metadata-invalid")
