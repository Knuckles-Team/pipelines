"""Validate public Pages URLs and map them to generated site paths."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

from .errors import _fail
from .url_security import _canonical_authority, _reject_private_host


def _invalid_origin(parsed: SplitResult, host: str, port: int | None) -> bool:
    if parsed.scheme != "https" or not host:
        return True
    return any(
        (
            parsed.username,
            parsed.password,
            port,
            parsed.query,
            parsed.fragment,
        )
    )


def _parse_public_url(raw: object, label: str) -> tuple[SplitResult, str]:
    if not isinstance(raw, str) or len(raw) > 2048:
        _fail(f"{label}-url-invalid")
    try:
        parsed = urlsplit(raw)
    except ValueError:
        _fail(f"{label}-url-invalid")
    host, port = _canonical_authority(parsed, label)
    if _invalid_origin(parsed, host, port):
        _fail(f"{label}-url-invalid")
    return parsed, host


def _url_path(parsed: SplitResult, label: str) -> str:
    path = unquote(parsed.path)
    if "\x00" in path or any(
        part in {"", ".", ".."} for part in path.split("/") if part
    ):
        _fail(f"{label}-path-invalid")
    if not path.startswith("/"):
        _fail(f"{label}-path-invalid")
    return path


def _public_url(raw: object, label: str) -> tuple[str, str, str]:
    """Validate a public HTTPS URL and return its scheme, host, and path."""

    parsed, host = _parse_public_url(raw, label)
    _reject_private_host(host, label)
    return parsed.scheme, host, _url_path(parsed, label)


def _site_remainder(url: str, site_url: str, label: str) -> tuple[str, str]:
    site_scheme, site_host, base_path = _public_url(site_url, "site-url")
    scheme, host, path = _public_url(url, label)
    if not base_path.endswith("/"):
        _fail("site-url-invalid")
    if (scheme, host) != (site_scheme, site_host):
        _fail("mirror-origin-mismatch")
    if not path.startswith(base_path):
        _fail(f"{label}-outside-site")
    return base_path, path[len(base_path) :]


def _html_output(parts: list[str], remainder: str) -> str:
    if not parts or remainder.endswith("/"):
        return PurePosixPath(*parts, "index.html").as_posix()
    suffix = PurePosixPath(parts[-1]).suffix
    if suffix == ".html":
        return PurePosixPath(*parts).as_posix()
    if suffix:
        _fail("canonical-path-invalid")
    return PurePosixPath(*parts[:-1], f"{parts[-1]}.html").as_posix()


def site_output_path(url: str, site_url: str, *, kind: str) -> str:
    """Map a published URL to the file ``mkdocs build --site-dir`` writes.

    ``site_url`` supplies the origin and base path. The base is stripped
    before the remainder is mapped to a relative file path. HTML directory
    URLs map to ``index.html``; extension-less leaves map to ``<leaf>.html``.
    Markdown URLs must name an ``index.md`` fallback.
    """

    if kind not in {"html", "markdown"}:
        _fail("site-output-kind-invalid")
    label = "canonical" if kind == "html" else "markdown"
    _, remainder = _site_remainder(url, site_url, label)
    parts = [part for part in remainder.split("/") if part]
    if kind == "markdown":
        if not parts or parts[-1] != "index.md":
            _fail("markdown-fallback-invalid")
        return PurePosixPath(*parts).as_posix()
    return _html_output(parts, remainder)


def _url_authority(host: str) -> str:
    return f"[{host}]" if ":" in host else host


def _site_asset_url(site_url: str, name: str) -> str:
    """Return a site-root asset URL such as ``llms.txt`` or ``sitemap.xml``."""

    scheme, host, base_path = _public_url(site_url, "site-url")
    if not base_path.endswith("/"):
        _fail("site-url-invalid")
    return urlunsplit(
        (scheme, _url_authority(host), f"{base_path}{name}", "", "")
    )
