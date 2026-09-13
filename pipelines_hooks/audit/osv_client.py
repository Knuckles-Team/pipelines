"""A bounded, redirect-refusing, proxy-free HTTPS client for the OSV API.

TLS trust is an environment concern (``SSL_CERT_FILE``/``REQUESTS_CA_BUNDLE``
for a PEM bundle, ``SSL_CERT_DIR`` for a hashed directory); certificate
verification is never disabled.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any

from pipelines_hooks.audit.acceptances import ADVISORY_RE
from pipelines_hooks.audit.lock import AuditError
from pipelines_hooks.core.settings import setting

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN_PREFIX = "https://api.osv.dev/v1/vulns/"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 30
UNAVAILABLE = "OSV service is unavailable"


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Any redirect surfaces as an HTTP error instead of being followed."""

    max_redirections = 0


def _tls_context() -> ssl.SSLContext:
    cafile = setting("SSL_CERT_FILE") or setting("REQUESTS_CA_BUNDLE") or None
    try:
        return ssl.create_default_context(cafile=cafile, capath=setting("SSL_CERT_DIR") or None)
    except (OSError, ssl.SSLError):
        raise AuditError("configured TLS trust material is invalid") from None


def _read_json(response: Any) -> dict[str, Any]:
    declared = response.headers.get("Content-Length")
    if declared and (not declared.isdigit() or int(declared) > MAX_RESPONSE_BYTES):
        raise AuditError("OSV response exceeds the safe bound or has an invalid length")
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise AuditError("OSV response exceeds the safe bound")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        raise AuditError("OSV response is invalid") from None
    if not isinstance(value, dict):
        raise AuditError("OSV response is invalid")
    return value


def _validated_target(url: str) -> None:
    if url != OSV_BATCH and not (url.startswith(OSV_VULN_PREFIX) and ADVISORY_RE.fullmatch(url.removeprefix(OSV_VULN_PREFIX))):
        raise AuditError("OSV request target is invalid")


def _open(prepared: urllib.request.Request) -> dict[str, Any]:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=_tls_context()), _NoRedirects()
    )
    with opener.open(prepared, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise AuditError("OSV service returned a non-success response")
        return _read_json(response)


def request(url: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET (or POST ``payload``) one fixed OSV endpoint."""
    _validated_target(url)
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Accept": "application/json", "User-Agent": "pipelines-hooks-audit/1"}
    headers.update({"Content-Type": "application/json"} if data is not None else {})
    try:
        return _open(urllib.request.Request(url, data=data, headers=headers))
    except urllib.error.HTTPError as exc:
        raise AuditError("OSV redirect was rejected" if 300 <= exc.code < 400 else UNAVAILABLE) from None
    except (urllib.error.URLError, TimeoutError, OSError, ssl.SSLError):
        raise AuditError(UNAVAILABLE) from None
