"""Validate and derive the HTML assets for a Pages Markdown delivery."""

from __future__ import annotations

import html
import re
from pathlib import Path

from .constants import (
    ATTRIBUTE_PATTERN,
    DEPRECATED_DATA_PATTERN,
    DIRECTIVE_MARKER_PATTERN,
    DIRECTIVE_PATTERN,
    LINK_TAG_PATTERN,
    MAX_GENERATED_FILE_BYTES,
    MAX_HTML_BYTES,
    META_TAG_PATTERN,
)
from .errors import _fail
from .filesystem import _regular_bytes
from .models import MirrorPage
from .privacy import _scan_safe_text
from .urls import _public_url, _site_asset_url


def _decode_html(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        _fail("html-invalid-encoding")


def _tag_attributes(tag: str) -> dict[str, str]:
    return {
        match.group("name").lower(): match.group("value")
        for match in ATTRIBUTE_PATTERN.finditer(tag)
    }


def _html_state(payload: bytes) -> str:
    text = _decode_html(payload)
    for tag in META_TAG_PATTERN.findall(text):
        attributes = _tag_attributes(tag)
        name = attributes.get("name", "").lower()
        content = attributes.get("content", "").lower()
        if name == "robots" and re.search(r"\bnoindex\b", content):
            return "noindex"
        if (
            name in {"agent-document-state", "document-state"}
            and content == "deprecated"
        ):
            return "deprecated"
    if DEPRECATED_DATA_PATTERN.search(text):
        return "deprecated"
    return "current"


def _markdown_alternate_hrefs(text: str) -> list[str]:
    hrefs: list[str] = []
    for tag in LINK_TAG_PATTERN.findall(text):
        attributes = _tag_attributes(tag)
        if (
            attributes.get("rel", "").lower() == "alternate"
            and attributes.get("type", "").lower() == "text/markdown"
        ):
            href = attributes.get("href")
            if href is None:
                _fail("html-alternate-invalid")
            hrefs.append(href)
    return hrefs


def _validate_alternate_hrefs(
    matches: list[str], markdown_url: str, expected: str
) -> None:
    if matches and any(
        value != markdown_url and value != expected for value in matches
    ):
        _fail("html-alternate-conflict")


def _validate_directive(text: str, expected: str, llms_url: str) -> bool:
    directive_matches = list(DIRECTIVE_PATTERN.finditer(text))
    if not DIRECTIVE_MARKER_PATTERN.search(text):
        return False
    if (
        len(directive_matches) != 1
        or len(DIRECTIVE_MARKER_PATTERN.findall(text)) != 1
    ):
        _fail("html-directive-invalid")
    directive = directive_matches[0]
    if directive.group("alternate") != expected or directive.group(
        "llms"
    ) != html.escape(llms_url, quote=True):
        _fail("html-directive-conflict")
    return True


def _html_with_alternate(
    page: MirrorPage, payload: bytes, llms_url: str
) -> tuple[bytes, str]:
    text = _decode_html(payload)
    matches = _markdown_alternate_hrefs(text)
    expected = html.escape(page.markdown_url, quote=True)
    _validate_alternate_hrefs(matches, page.markdown_url, expected)
    has_alternate = page.markdown_url in matches or expected in matches
    has_directive = _validate_directive(text, expected, llms_url)

    additions: list[str] = []
    if not has_alternate:
        additions.append(
            f'  <link rel="alternate" type="text/markdown" href="{expected}">\n'
        )
    if not has_directive:
        additions.append(
            "  <!-- agent-utilities-markdown "
            f'alternate="{expected}" llms="{html.escape(llms_url, quote=True)}" -->\n'
        )
    if not additions:
        return payload, _html_state(payload)
    if re.search(r"</head\s*>", text, re.IGNORECASE) is None:
        _fail("html-head-missing")
    updated = re.sub(
        r"</head\s*>",
        "".join(additions) + "</head>",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    return updated.encode("utf-8"), _html_state(payload)


def _robots_sitemap_indexes(text: str, sitemap_url: str) -> list[int]:
    indexes: list[int] = []
    for index, line in enumerate(text.splitlines(keepends=True)):
        body = line.rstrip("\r\n")
        match = re.fullmatch(r"\s*sitemap\s*:\s*(.*?)\s*", body, re.IGNORECASE)
        if match is None:
            continue
        value = match.group(1)
        if not value:
            _fail("robots-sitemap-invalid")
        _public_url(value, "robots-sitemap")
        if value != sitemap_url:
            _fail("robots-sitemap-conflict")
        indexes.append(index)
    return indexes


def _robots_with_sitemap(site: Path, sitemap_url: str) -> bytes:
    sitemap_line = f"Sitemap: {sitemap_url}\n"
    robots_path = site / "robots.txt"
    if robots_path.is_symlink():
        _fail("robots-policy-symlink")
    if not robots_path.exists():
        return sitemap_line.encode("utf-8")
    payload = _regular_bytes(robots_path, "robots-policy", MAX_GENERATED_FILE_BYTES)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        _fail("robots-policy-invalid-encoding")
    _scan_safe_text(text, "robots-policy")
    lines = text.splitlines(keepends=True)
    sitemap_indexes = _robots_sitemap_indexes(text, sitemap_url)
    if len(sitemap_indexes) > 1:
        _fail("robots-sitemap-duplicate")
    if sitemap_indexes:
        lines[sitemap_indexes[0]] = sitemap_line
        return "".join(lines).encode("utf-8")
    separator = "" if not text or text.endswith(("\n", "\r")) else "\n"
    return (text + separator + sitemap_line).encode("utf-8")


def _derived_assets(
    pages: tuple[MirrorPage, ...], site: Path, site_url: str
) -> tuple[tuple[Path, bytes], ...]:
    sitemap_url = _site_asset_url(site_url, "sitemap.xml")
    sitemap_rows: list[str] = []
    for page in pages:
        state = _html_state(
            _regular_bytes(page.html_path, "html-output", MAX_HTML_BYTES)
        )
        if state == "current":
            sitemap_rows.append(
                f"  <url><loc>{html.escape(page.canonical_url)}</loc></url>"
            )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(sitemap_rows)
        + "\n</urlset>\n"
    ).encode("utf-8")
    robots = _robots_with_sitemap(site, sitemap_url)
    return (
        (site / ".nojekyll", b""),
        (site / "robots.txt", robots),
        (site / "sitemap.xml", sitemap),
    )
