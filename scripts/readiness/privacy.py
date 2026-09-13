"""Reject private endpoints and secret-like values in readiness metadata."""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import unquote, urlsplit

from .constants import BEARER_PATTERN, SECRET_PATTERN, URL_PATTERN
from .errors import _fail
from .ip_addresses import _private_address


def _private_hostname(host: str) -> bool:
    return host in {"localhost", "local", "internal"} or host.endswith(
        (".local", ".localhost", ".internal", ".home", ".arpa")
    )


def _reject_private_host(host: str, label: str) -> None:
    """Reject local names and non-public IP address literals."""

    decoded = unquote(host).rstrip(".").lower()
    if _private_hostname(decoded) or _private_address(decoded):
        _fail(f"{label}-private-url")


def _scan_url(raw: str, label: str) -> None:
    """Validate credentials, query secrets, and private hosts in one URL."""

    try:
        parsed = urlsplit(raw)
        host = parsed.hostname.rstrip(".").lower() if parsed.hostname else ""
    except ValueError:
        _fail(f"{label}-url-invalid")
    if parsed.username or parsed.password:
        _fail(f"{label}-credential-url")
    if parsed.query and re.search(
        r"(?i)(?:token|secret|password|api[_-]?key|credential|auth)=",
        parsed.query,
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
