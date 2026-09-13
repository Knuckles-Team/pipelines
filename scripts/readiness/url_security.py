"""Canonical URL privacy checks shared by metadata and structured URLs."""

from __future__ import annotations

import re
from urllib.parse import SplitResult, unquote, urlsplit

from .constants import BEARER_PATTERN, SECRET_PATTERN, URL_PATTERN
from .errors import _fail
from .ip_addresses import _private_address


_INVALID_PERCENT_PATTERN = re.compile(r"%(?![0-9A-Fa-f]{2})")
_VALID_PERCENT_PATTERN = re.compile(r"%[0-9A-Fa-f]{2}")
_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?:token|secret|password|api[_-]?key|credential|auth)\s*="
)
_MAX_DECODE_PASSES = 3
_MAX_NESTED_URLS = 16


def _canonical_component(raw: str, label: str) -> str:
    """Strictly decode nested percent escapes to a bounded fixed point."""

    current = raw
    for _ in range(_MAX_DECODE_PASSES):
        if _INVALID_PERCENT_PATTERN.search(current):
            _fail(f"{label}-url-invalid")
        try:
            decoded = unquote(current, errors="strict")
        except UnicodeDecodeError:
            _fail(f"{label}-url-invalid")
        if not _VALID_PERCENT_PATTERN.search(decoded):
            return decoded
        current = decoded
    _fail(f"{label}-url-invalid")


def _private_hostname(host: str) -> bool:
    return host in {"localhost", "local", "internal"} or host.endswith(
        (".local", ".localhost", ".internal", ".home", ".arpa")
    )


def _reject_private_host(host: str, label: str) -> None:
    """Reject local names and canonicalized non-public IP address literals."""

    decoded = _canonical_component(host, label).rstrip(".").lower()
    if _private_hostname(decoded) or _private_address(decoded):
        _fail(f"{label}-private-url")


def _invalid_authority(authority: str) -> bool:
    return any(
        character.isspace() or character in "/?#\\" for character in authority
    )


def _decoded_authority(
    parsed: SplitResult, authority: str, label: str
) -> tuple[str, int | None]:
    """Validate canonical authority syntax and return its normalized host."""

    if _invalid_authority(authority):
        _fail(f"{label}-url-invalid")
    try:
        decoded = urlsplit(f"//{authority}")
        host = decoded.hostname.rstrip(".").lower() if decoded.hostname else ""
        port = decoded.port
    except ValueError:
        _fail(f"{label}-url-invalid")
    if not host:
        _fail(f"{label}-url-invalid")
    if parsed.username or parsed.password or decoded.username or decoded.password:
        _fail(f"{label}-credential-url")
    return host, port


def _canonical_authority(parsed: SplitResult, label: str) -> tuple[str, int | None]:
    """Return the host and port from one strictly decoded URL authority."""

    authority = _canonical_component(parsed.netloc, label)
    return _decoded_authority(parsed, authority, label)


def _reject_component_credentials(value: str, label: str) -> None:
    """Reject credential assignments and bearer values in any URL component."""

    if _CREDENTIAL_PATTERN.search(value):
        _fail(f"{label}-credential-url")
    if SECRET_PATTERN.search(value) or BEARER_PATTERN.search(value):
        _fail(f"{label}-secret-like-value")


def _validated_components(raw: str, label: str) -> tuple[str, ...]:
    """Canonicalize one URL and validate its decoded authority and host."""

    try:
        parsed = urlsplit(raw)
    except ValueError:
        _fail(f"{label}-url-invalid")
    components = tuple(
        _canonical_component(component, label)
        for component in (parsed.netloc, parsed.path, parsed.query, parsed.fragment)
    )
    authority, _, _, _ = components
    host, _ = _decoded_authority(parsed, authority, label)
    _reject_private_host(host, label)
    return components


def _trim_candidate(raw: str, label: str) -> str:
    """Remove prose punctuation and reject unmatched URL brackets."""

    candidate = raw.rstrip(".,;:")
    if candidate.count("[") != candidate.count("]"):
        _fail(f"{label}-url-invalid")
    return candidate


def _scan_url(raw: str, label: str) -> None:
    """Validate one URL and any URLs revealed by component decoding."""

    pending = [_trim_candidate(raw, label)]
    seen: set[str] = set()
    while pending:
        candidate = pending.pop()
        if candidate in seen:
            continue
        seen.add(candidate)
        if len(seen) > _MAX_NESTED_URLS:
            _fail(f"{label}-url-invalid")
        components = _validated_components(candidate, label)
        for component in components:
            _reject_component_credentials(component, label)
            pending.extend(
                _INVALID_PERCENT_PATTERN.sub(
                    "%25", _trim_candidate(match.group(0), label)
                )
                for match in URL_PATTERN.finditer(component)
            )
