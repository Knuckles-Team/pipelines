"""Local-link and offline URL validation for the public documentation gate."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pipelines_hooks.docs.public_surface_constants import (
    LINK_RE,
    WINDOWS_ABSOLUTE_RE,
)
from pipelines_hooks.core.errors import CannotRun


def _public_host(host: str, label: str) -> None:
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".arpa")):
        raise CannotRun(f"{label} must not target a local hostname")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:  # noqa: BLE001 - hostnames are valid when they are not IP literals
        return
    if address.is_private or address.is_loopback or address.is_reserved:
        raise CannotRun(f"{label} must not target a private or reserved address")


def public_url(value: str, label: str) -> str:
    """Validate URL syntax without performing a network request."""
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
        raise CannotRun(f"{label} must be an HTTPS URL without credentials")
    _public_host(host, label)
    return value.rstrip("/") or value


def link_destination(raw: str) -> str:
    """Extract a Markdown link destination, including angle-bracket URLs."""
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value


def local_link_findings(root: Path, text: str) -> list[str]:
    """Reject local links that escape the repository or point nowhere."""
    findings: list[str] = []
    root = root.resolve()
    for match in LINK_RE.finditer(text):
        destination = link_destination(match.group(1))
        parsed = urlsplit(destination)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme.lower() not in {"http", "https", "mailto", "tel"}:
                findings.append(f"README link uses a forbidden URL scheme: {destination!r}")
            continue
        path = unquote(parsed.path)
        if not path:
            continue
        portable_path = path.replace("\\", "/")
        if portable_path.startswith("/") or WINDOWS_ABSOLUTE_RE.match(portable_path):
            findings.append(f"README local link is absolute: {destination!r}")
            continue
        target = (root / portable_path).resolve()
        if not target.is_relative_to(root):
            findings.append(f"README local link escapes the repository: {destination!r}")
        elif not target.exists():
            findings.append(f"README local link does not exist: {destination!r}")
    return findings
