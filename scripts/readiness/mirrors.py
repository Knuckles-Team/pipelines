"""Validate canonical source pages and build their delivery records.

The source mirror is the trust boundary between the generated manifest and the
published site.  This module keeps that boundary small: manifest shape,
provenance, source bytes, and output paths are checked before a ``MirrorPage``
is returned to the delivery planner.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple, cast

from . import constants, errors, filesystem, models, privacy, urls


class MirrorEntry(NamedTuple):
    """Validated scalar fields from one mirror manifest entry."""

    source: str
    canonical: str
    markdown_url: str
    digest: str
    size: int


def _validate_manifest(manifest: Mapping[str, Any]) -> list[Any]:
    """Return the declared entries after checking the mirror contract."""

    if (
        set(manifest)
        != {"schema_version", "url_contract", "applicable", "entries"}
        or manifest.get("schema_version") != constants.SCHEMA_VERSION
        or manifest.get("url_contract") != constants.MIRROR_CONTRACT
        or manifest.get("applicable") is not True
    ):
        errors._fail("mirror-contract-invalid")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > constants.MAX_ENTRIES:
        errors._fail("mirror-entries-invalid")
    return entries


def _provenance_index(
    readiness_manifest: Mapping[str, Any], *, entry_count: int
) -> dict[str, tuple[str, int]]:
    """Index source provenance while retaining its exact validation errors."""

    provenance = readiness_manifest.get("provenance")
    pages = provenance.get("pages") if isinstance(provenance, Mapping) else None
    if not isinstance(pages, list) or len(pages) != entry_count:
        errors._fail("provenance-pages-invalid")
    indexed: dict[str, tuple[str, int]] = {}
    for item in pages:
        source, digest, size = _provenance_item(item)
        if source in indexed:
            errors._fail("provenance-pages-duplicate")
        indexed[source] = (digest, size)
    return indexed


def _provenance_item(item: object) -> tuple[str, str, int]:
    """Validate one readiness provenance page."""

    if not isinstance(item, Mapping):
        errors._fail("provenance-pages-invalid")
    source = item.get("source")
    digest = item.get("sha256")
    size = item.get("bytes")
    if not isinstance(source, str) or not isinstance(digest, str):
        errors._fail("provenance-pages-invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors._fail("provenance-pages-invalid")
    if type(size) is not int or size < 0:
        errors._fail("provenance-pages-invalid")
    return source, digest, size


def _entry_mapping(raw: object) -> Mapping[str, Any]:
    """Validate an entry's exact manifest key set."""

    if not isinstance(raw, Mapping):
        errors._fail("mirror-entry-invalid")
    if set(raw) != {
        "source",
        "url",
        "canonical_url",
        "markdown_url",
        "sha256",
        "bytes",
    }:
        errors._fail("mirror-entry-invalid")
    return raw


def _entry_values(raw: Mapping[str, Any]) -> MirrorEntry:
    """Validate the scalar values in one manifest entry."""

    text_values = tuple(
        raw.get(key) for key in ("source", "url", "canonical_url", "markdown_url")
    )
    if not all(isinstance(value, str) for value in text_values):
        errors._fail("mirror-entry-invalid")
    source, url, canonical, markdown_url = text_values
    if canonical != url:
        errors._fail("mirror-entry-invalid")
    digest = raw.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors._fail("mirror-entry-invalid")
    size = raw.get("bytes")
    if type(size) is not int or size < 0 or size > constants.MAX_SOURCE_BYTES:
        errors._fail("mirror-entry-invalid")
    return MirrorEntry(
        cast(str, source),
        cast(str, canonical),
        cast(str, markdown_url),
        digest,
        size,
    )


def _validate_entry(raw: object) -> MirrorEntry:
    """Validate one manifest entry and return its fields in stable order."""

    return _entry_values(_entry_mapping(raw))


def _source_payload(
    root: Path,
    site: Path,
    source: str,
    *,
    digest: str,
    size: int,
    provenance_index: Mapping[str, tuple[str, int]],
) -> tuple[Path, bytes]:
    """Read and verify one source page against both manifest authorities."""

    source_path = filesystem._safe_existing_path(root, source, "source")
    if site in source_path.parents or source_path == site:
        errors._fail("source-site-recursion")
    source_bytes = filesystem._regular_bytes(
        source_path, "source", constants.MAX_SOURCE_BYTES
    )
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        errors._fail("source-invalid-encoding")
    if constants.DIRECTIVE_MARKER_PATTERN.search(source_text):
        errors._fail("source-agent-directive")
    privacy._scan_safe_text(source_text, "source")
    if len(source_bytes) != size or hashlib.sha256(source_bytes).hexdigest() != digest:
        errors._fail("source-digest-stale")
    if provenance_index[source] != (digest, size):
        errors._fail("provenance-digest-stale")
    return source_path, source_bytes


def _output_paths(
    site: Path,
    canonical: str,
    markdown_url: str,
    *,
    site_url: str,
    seen_markdown: set[Path],
    seen_html: set[Path],
) -> tuple[Path, Path]:
    """Resolve and validate the two site outputs for a source page."""

    markdown_relative = urls.site_output_path(markdown_url, site_url, kind="markdown")
    markdown_local = filesystem._safe_output_path(
        site, markdown_relative, "markdown-output"
    )
    html_relative = urls.site_output_path(canonical, site_url, kind="html")
    html_local = filesystem._safe_output_path(site, html_relative, "html-output")
    if markdown_local in seen_markdown or html_local in seen_html:
        errors._fail("mirror-output-duplicate")
    filesystem._regular_bytes(html_local, "html-output", constants.MAX_HTML_BYTES)
    return markdown_local, html_local


def _manifest_page(
    root: Path,
    site: Path,
    entry: MirrorEntry,
    *,
    site_url: str,
    provenance_index: Mapping[str, tuple[str, int]],
    seen_markdown: set[Path],
    seen_html: set[Path],
) -> models.MirrorPage:
    """Build one fully validated mirror page."""

    source, canonical, markdown_url, digest, size = entry
    source_path, source_bytes = _source_payload(
        root,
        site,
        source,
        digest=digest,
        size=size,
        provenance_index=provenance_index,
    )
    markdown_local, html_local = _output_paths(
        site,
        canonical,
        markdown_url,
        site_url=site_url,
        seen_markdown=seen_markdown,
        seen_html=seen_html,
    )
    return models.MirrorPage(
        source=source,
        canonical_url=canonical,
        markdown_url=markdown_url,
        digest=digest,
        size=size,
        source_bytes=source_bytes,
        source_path=source_path,
        html_path=html_local,
        markdown_path=markdown_local,
    )


def _source_manifest_pages(
    root: Path,
    site: Path,
    site_url: str,
    *,
    mirror_manifest: Mapping[str, Any],
    readiness_manifest: Mapping[str, Any],
) -> tuple[models.MirrorPage, ...]:
    """Validate a mirror manifest and return its source delivery pages."""

    entries = _validate_manifest(mirror_manifest)
    provenance_index = _provenance_index(
        readiness_manifest, entry_count=len(entries)
    )
    pages: list[models.MirrorPage] = []
    seen_sources: set[str] = set()
    seen_markdown: set[Path] = set()
    seen_html: set[Path] = set()
    total_source_bytes = 0
    for raw_entry in entries:
        entry = _validate_entry(raw_entry)
        source = entry[0]
        if source in seen_sources or source not in provenance_index:
            errors._fail("mirror-entry-duplicate")
        page = _manifest_page(
            root,
            site,
            entry,
            site_url=site_url,
            provenance_index=provenance_index,
            seen_markdown=seen_markdown,
            seen_html=seen_html,
        )
        total_source_bytes += len(page.source_bytes)
        if total_source_bytes > constants.MAX_TOTAL_SOURCE_BYTES:
            errors._fail("source-total-oversize")
        pages.append(page)
        seen_sources.add(source)
        seen_markdown.add(page.markdown_path)
        seen_html.add(page.html_path)
    if set(provenance_index) != seen_sources:
        errors._fail("provenance-pages-incomplete")
    return tuple(pages)
