#!/usr/bin/env python3
"""Build and verify the canonical Pages Markdown delivery contract.

CONCEPT:ECO-4.DOCS-DELIVERY — Deterministic source-Markdown Pages delivery.

This helper consumes the two artifacts emitted by the universal-skills
agent-readiness generator.  It never converts HTML back into Markdown and it
does not define a replacement manifest or capability schema.  The helper only
materializes the generator's declared ``index.md`` fallbacks and derives
bounded crawl/HTML assets after those mirrors have been proven current.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import ipaddress
import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn
from urllib.parse import unquote, urlsplit, urlunsplit

SCHEMA_ID = "https://agent-utilities.invalid/schemas/agent-readiness-v1.json"
SCHEMA_VERSION = "agent-readiness/v1"
MIRROR_CONTRACT = "mkdocs-static/v2"
CHECKER_VERSION = "pages-readiness-tck/v1"

MAX_ENTRIES = 512
MAX_SOURCE_BYTES = 2_000_000
MAX_TOTAL_SOURCE_BYTES = 8_000_000
MAX_GENERATED_FILE_BYTES = 500_000
MAX_TOTAL_GENERATED_BYTES = 8_000_000
MAX_HTML_BYTES = 8_000_000
MAX_MANIFEST_BYTES = 1_000_000

APPLICABILITY_KEYS = {
    "content",
    "discoverability",
    "access_policy",
    "capabilities",
    "errors",
    "provenance",
    "measurement",
    "deployment",
}
CAPABILITY_KEYS = {"api", "mcp", "a2a", "skills"}
SIGNAL_POLICIES = {"unset", "operator-reviewed"}
STANDARD_KINDS = {"rfc", "draft", "convention"}
GENERATOR_OUTPUTS = {
    "llms.txt",
    "llms-full.txt",
    "llms-sections",
    "markdown-mirror-manifest.json",
    "agent-readiness-manifest.json",
}
SECRET_PATTERN = re.compile(
    r"(?ix)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|"
    r"secret(?:[_-][a-z0-9]+)*|token(?:[_-][a-z0-9]+)*)"
    r"[\"'`]?\s*[:=]\s*(?!<|\$|env://|\*|redacted\b|none\b|false\b|true\b)"
    r"[\"']?[A-Za-z0-9_./+=:-]{12,}[\"']?"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")
URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")
META_TAG_PATTERN = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
DEPRECATED_DATA_PATTERN = re.compile(
    r"data-(?:agent-)?document-state\s*=\s*[\"']deprecated[\"']",
    re.IGNORECASE,
)
LINK_TAG_PATTERN = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
DIRECTIVE_MARKER_PATTERN = re.compile(
    r"<!--\s*agent-utilities-markdown\b", re.IGNORECASE
)
DIRECTIVE_PATTERN = re.compile(
    r"<!--\s*agent-utilities-markdown\s+"
    r'alternate="(?P<alternate>[^"]+)"\s+'
    r'llms="(?P<llms>[^"]+)"\s*-->',
    re.IGNORECASE,
)
ATTRIBUTE_PATTERN = re.compile(
    r"(?P<name>[a-z][a-z0-9:-]*)\s*=\s*(?P<quote>[\"'])(?P<value>[^\"']*)(?P=quote)",
    re.IGNORECASE,
)


class ReadinessTckError(ValueError):
    """A bounded, privacy-safe offline readiness failure."""


@dataclass(frozen=True)
class MirrorPage:
    """One page declared by the canonical Markdown mirror manifest."""

    source: str
    canonical_url: str
    markdown_url: str
    digest: str
    size: int
    source_bytes: bytes
    source_path: Path
    html_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class DeliveryPlan:
    """Validated source mirrors and derived static assets."""

    pages: tuple[MirrorPage, ...]
    mirrors: tuple[tuple[Path, bytes], ...]
    html: tuple[tuple[Path, bytes], ...]
    assets: tuple[tuple[Path, bytes], ...]
    manifest_digest: str


def _fail(code: str) -> NoReturn:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", code):
        code = "readiness-contract-invalid"
    raise ReadinessTckError(code)


def _safe_root(value: str | Path) -> Path:
    root = Path(value).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    try:
        resolved = root.resolve(strict=True)
        metadata = root.lstat()
    except (OSError, RuntimeError):
        _fail("root-unavailable")
    if root.is_symlink() or resolved != root.absolute() or not root.is_dir():
        _fail("root-invalid")
    if metadata.st_nlink < 1:
        _fail("root-invalid")
    return resolved


def _path_parts(raw: object, label: str) -> tuple[str, ...]:
    if isinstance(raw, Path):
        raw = raw.as_posix()
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        _fail(f"{label}-path-invalid")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or not relative.parts:
        _fail(f"{label}-path-invalid")
    if any(
        part in {"", ".", ".."} or any(ord(char) < 32 for char in part)
        for part in relative.parts
    ):
        _fail(f"{label}-path-invalid")
    return relative.parts


def _reject_symlink_components(root: Path, candidate: Path, label: str) -> None:
    try:
        relative = candidate.absolute().relative_to(root.absolute())
    except ValueError:
        _fail(f"{label}-containment")
    cursor = root
    for part in relative.parts:
        cursor /= part
        try:
            if cursor.is_symlink():
                _fail(f"{label}-symlink")
        except OSError:
            _fail(f"{label}-unavailable")


def _safe_existing_path(root: Path, raw: object, label: str) -> Path:
    parts = _path_parts(raw, label)
    candidate = root.joinpath(*parts)
    _reject_symlink_components(root, candidate, label)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        _fail(f"{label}-containment")
    return resolved


def _safe_existing_dir(root: Path, raw: object, label: str) -> Path:
    path = _safe_existing_path(root, raw, label)
    if not path.is_dir() or path.is_symlink():
        _fail(f"{label}-not-directory")
    return path


def _safe_site(root: Path, raw: str | Path) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        return _safe_existing_path(root, candidate, "site")
    _reject_symlink_components(root, candidate, "site")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        _fail("site-containment")
    if resolved.is_symlink() or not resolved.is_dir():
        _fail("site-invalid")
    return resolved


def _regular_bytes(path: Path, label: str, limit: int) -> bytes:
    try:
        metadata = path.lstat()
    except OSError:
        _fail(f"{label}-unavailable")
    if path.is_symlink() or not path.is_file() or metadata.st_nlink != 1:
        _fail(f"{label}-not-regular")
    if metadata.st_size > limit:
        _fail(f"{label}-oversize")
    try:
        payload = path.read_bytes()
    except OSError:
        _fail(f"{label}-unreadable")
    if len(payload) > limit:
        _fail(f"{label}-oversize")
    return payload


def _read_json(
    path: Path, label: str, limit: int = MAX_MANIFEST_BYTES
) -> dict[str, Any]:
    payload = _regular_bytes(path, label, limit)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(f"{label}-invalid-json")
    if not isinstance(value, dict):
        _fail(f"{label}-root-invalid")
    return value


def _safe_output_path(site: Path, relative: str, label: str) -> Path:
    parts = _path_parts(relative, label)
    candidate = site.joinpath(*parts)
    _reject_symlink_components(site, candidate, label)
    try:
        candidate.absolute().relative_to(site.absolute())
    except ValueError:
        _fail(f"{label}-containment")
    if candidate.exists() and candidate.is_symlink():
        _fail(f"{label}-symlink")
    if candidate.exists() and not candidate.is_file():
        _fail(f"{label}-not-regular")
    return candidate


def _atomic_write(path: Path, payload: bytes, label: str) -> None:
    parent = path.parent
    _reject_symlink_components(parent.parent, parent, label)
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        _fail(f"{label}-parent-invalid")
    parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _regular_bytes(path, label, max(len(payload), MAX_HTML_BYTES))
        if path.read_bytes() == payload:
            return
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        _fail(f"{label}-write-failed")
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _public_url(raw: object, label: str) -> tuple[str, str, str]:
    if not isinstance(raw, str) or len(raw) > 2048:
        _fail(f"{label}-url-invalid")
    try:
        parsed = urlsplit(raw)
        host = parsed.hostname.rstrip(".").lower() if parsed.hostname else ""
        port = parsed.port
    except ValueError:
        _fail(f"{label}-url-invalid")
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or port
        or parsed.query
        or parsed.fragment
    ):
        _fail(f"{label}-url-invalid")
    if host in {"localhost", "local", "internal"} or host.endswith(
        (".local", ".localhost", ".internal", ".home", ".arpa")
    ):
        _fail(f"{label}-private-url")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        or address.is_multicast
    ):
        _fail(f"{label}-private-url")
    path = unquote(parsed.path)
    if "\x00" in path or any(
        part in {"", ".", ".."} for part in path.split("/") if part
    ):
        _fail(f"{label}-path-invalid")
    if not path.startswith("/"):
        _fail(f"{label}-path-invalid")
    return parsed.scheme, host, path


def _scan_safe_text(value: object, label: str) -> None:
    if isinstance(value, str):
        if SECRET_PATTERN.search(value) or BEARER_PATTERN.search(value):
            _fail(f"{label}-secret-like-value")
        for match in URL_PATTERN.finditer(value):
            raw = match.group(0).rstrip(".,;:")
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
            if host in {"localhost", "local", "internal"} or host.endswith(
                (".local", ".localhost", ".internal", ".home", ".arpa")
            ):
                _fail(f"{label}-private-url")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_reserved
                or address.is_unspecified
                or address.is_multicast
            ):
                _fail(f"{label}-private-url")
    elif isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                _fail(f"{label}-metadata-invalid")
            _scan_safe_text(child, label)
    elif isinstance(value, list):
        for child in value:
            _scan_safe_text(child, label)
    elif value is not None and not isinstance(value, (bool, int, float)):
        _fail(f"{label}-metadata-invalid")


def _validate_schema(schema: Mapping[str, Any]) -> set[str]:
    if schema.get("$id") != SCHEMA_ID or schema.get("type") != "object":
        _fail("schema-authority-invalid")
    if schema.get("additionalProperties") is not False:
        _fail("schema-additional-properties")
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        _fail("schema-shape-invalid")
    required_set = {item for item in required if isinstance(item, str)}
    expected = {
        "schema_version",
        "project",
        "applicability",
        "standards",
        "content_signals",
        "budgets",
        "capabilities",
    }
    if required_set != expected or set(properties) != expected:
        _fail("schema-authority-invalid")
    version = properties.get("schema_version")
    if not isinstance(version, Mapping) or version.get("const") != SCHEMA_VERSION:
        _fail("schema-authority-invalid")
    return required_set


def _validate_readiness_input(
    value: Mapping[str, Any], schema: Mapping[str, Any]
) -> dict[str, Any]:
    required = _validate_schema(schema)
    if set(value) != required or value.get("schema_version") != SCHEMA_VERSION:
        _fail("readiness-schema-mismatch")
    project = value.get("project")
    if (
        not isinstance(project, Mapping)
        or set(project) != {"name", "kind"}
        or not isinstance(project.get("name"), str)
        or not project["name"]
        or project.get("kind") not in {"library", "package", "service", "docs-only"}
    ):
        _fail("readiness-project-invalid")
    applicability = value.get("applicability")
    if (
        not isinstance(applicability, Mapping)
        or set(applicability) != APPLICABILITY_KEYS
        or any(type(applicability[key]) is not bool for key in APPLICABILITY_KEYS)
    ):
        _fail("readiness-applicability-invalid")
    standards = value.get("standards")
    if not isinstance(standards, list) or not standards:
        _fail("readiness-standards-invalid")
    standard_ids: set[str] = set()
    for standard in standards:
        if not isinstance(standard, Mapping) or set(standard) != {
            "id",
            "kind",
            "level",
        }:
            _fail("readiness-standards-invalid")
        identifier = standard.get("id")
        kind = standard.get("kind")
        level = standard.get("level")
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .:_/-]{1,127}", identifier)
            or identifier in standard_ids
            or kind not in STANDARD_KINDS
            or level not in {"normative", "draft", "advisory"}
            or (kind == "rfc" and level != "normative")
            or (kind == "draft" and level == "normative")
        ):
            _fail("readiness-standards-invalid")
        standard_ids.add(identifier)
    signals = value.get("content_signals")
    if not isinstance(signals, Mapping) or set(signals) - {"policy", "values"}:
        _fail("content-signals-policy-required")
    policy = signals.get("policy")
    if policy not in SIGNAL_POLICIES:
        _fail("content-signals-policy-required")
    if policy == "unset" and "values" in signals:
        _fail("content-signals-values-unset")
    if policy == "operator-reviewed" and not isinstance(signals.get("values"), Mapping):
        _fail("content-signals-values-required")
    _scan_safe_text(signals, "content-signals")
    budgets = value.get("budgets")
    if not isinstance(budgets, Mapping) or set(budgets) - {
        "curated_chars",
        "summary_chars",
        "full_chars",
    }:
        _fail("readiness-budgets-invalid")
    for key, limit in (
        ("curated_chars", 32_000),
        ("summary_chars", 1_200),
        ("full_chars", 500_000),
    ):
        number = budgets.get(key, 0 if key == "full_chars" else None)
        if (
            type(number) is not int
            or not 0 <= number <= limit
            or (key != "full_chars" and number < 1)
        ):
            _fail("readiness-budgets-invalid")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, Mapping) or set(capabilities) != CAPABILITY_KEYS:
        _fail("capabilities-invalid")
    for name, raw in capabilities.items():
        if not isinstance(raw, Mapping) or not isinstance(raw.get("applicable"), bool):
            _fail("capability-entry-invalid")
        applicable = raw["applicable"]
        allowed = (
            {"applicable", "path"}
            if name == "skills"
            else {"applicable", "artifact", "endpoint"}
        )
        if set(raw) - allowed:
            _fail("capability-entry-invalid")
        if not applicable and set(raw) != {"applicable"}:
            _fail("capability-entry-inapplicable-data")
        if applicable and name == "skills" and not isinstance(raw.get("path"), str):
            _fail("skills-path-required")
        if applicable and name != "skills" and not isinstance(raw.get("artifact"), str):
            _fail("capability-authority-required")
        endpoint = raw.get("endpoint")
        if applicable and name in {"mcp", "a2a"} and not isinstance(endpoint, str):
            _fail("capability-endpoint-required")
        if endpoint is not None:
            _public_url(endpoint, f"{name}-endpoint")
        _scan_safe_text(raw, f"{name}-capability")
    _scan_safe_text(value, "readiness")
    return {
        "schema_version": SCHEMA_VERSION,
        "content_signals": json.loads(json.dumps(signals, sort_keys=True)),
    }


def _validate_generated_outputs(
    root: Path, manifest: Mapping[str, Any]
) -> tuple[tuple[str, bytes], ...]:
    generated = manifest.get("generated")
    if not isinstance(generated, list) or not generated or len(generated) > 256:
        _fail("generated-list-invalid")
    normalized: list[str] = []
    for raw in generated:
        if not isinstance(raw, str) or "\\" in raw:
            _fail("generated-path-invalid")
        parts = _path_parts(raw, "generated")
        if parts[0] not in GENERATOR_OUTPUTS:
            _fail("generated-path-outside-contract")
        if parts[0] != "llms-sections" and len(parts) != 1:
            _fail("generated-path-invalid")
        if parts[0] == "llms-sections" and (len(parts) < 2 or parts[-1] != "llms.txt"):
            _fail("generated-path-invalid")
        normalized.append(PurePosixPath(*parts).as_posix())
    if len(set(normalized)) != len(normalized):
        _fail("generated-path-duplicate")
    if (
        "llms.txt" not in normalized
        or "markdown-mirror-manifest.json" not in normalized
    ):
        _fail("generated-output-missing")
    if "agent-readiness-manifest.json" in normalized:
        _fail("generated-path-invalid")
    total = 0
    published: list[tuple[str, bytes]] = []
    for relative in normalized:
        path = root.joinpath(*PurePosixPath(relative).parts)
        payload = _regular_bytes(path, "generated-output", MAX_GENERATED_FILE_BYTES)
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            _fail("generated-output-invalid-encoding")
        _scan_safe_text(text, "generated-output")
        total += len(payload)
        if (
            relative == "llms.txt"
            or relative == "llms-full.txt"
            or relative.startswith("llms-sections/")
        ):
            published.append((relative, payload))
    if total > MAX_TOTAL_GENERATED_BYTES:
        _fail("generated-output-oversize")
    return tuple(published)


def _validate_capability_paths(root: Path, value: Mapping[str, Any]) -> None:
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, Mapping):
        _fail("capabilities-invalid")
    for name, raw in capabilities.items():
        if not isinstance(raw, Mapping) or raw.get("applicable") is not True:
            continue
        if name == "skills":
            _safe_existing_dir(root, raw.get("path"), "skills-path")
            continue
        artifact = _safe_existing_path(root, raw.get("artifact"), f"{name}-artifact")
        metadata = _read_json(artifact, f"{name}-artifact")
        if set(metadata) - {"applicable", "surface", "source", "version"}:
            _fail("capability-artifact-schema-invalid")
        if metadata.get("applicable") is not True or metadata.get("surface") != name:
            _fail("capability-artifact-unproven")
        source = metadata.get("source")
        if not isinstance(source, str):
            _fail("capability-artifact-source-invalid")
        _regular_bytes(
            _safe_existing_path(root, source, f"{name}-artifact-source"),
            f"{name}-artifact-source",
            MAX_SOURCE_BYTES,
        )
        _scan_safe_text(metadata, f"{name}-artifact")


def _source_manifest_pages(
    root: Path,
    site: Path,
    mirror_manifest: Mapping[str, Any],
    readiness_manifest: Mapping[str, Any],
) -> tuple[MirrorPage, ...]:
    if (
        set(mirror_manifest)
        != {"schema_version", "url_contract", "applicable", "entries"}
        or mirror_manifest.get("schema_version") != SCHEMA_VERSION
        or mirror_manifest.get("url_contract") != MIRROR_CONTRACT
        or mirror_manifest.get("applicable") is not True
    ):
        _fail("mirror-contract-invalid")
    entries = mirror_manifest.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_ENTRIES:
        _fail("mirror-entries-invalid")
    provenance = readiness_manifest.get("provenance")
    provenance_pages = (
        provenance.get("pages") if isinstance(provenance, Mapping) else None
    )
    if not isinstance(provenance_pages, list) or len(provenance_pages) != len(entries):
        _fail("provenance-pages-invalid")
    provenance_index: dict[str, tuple[str, int]] = {}
    for item in provenance_pages:
        if not isinstance(item, Mapping):
            _fail("provenance-pages-invalid")
        source = item.get("source")
        digest = item.get("sha256")
        size = item.get("bytes")
        if (
            not isinstance(source, str)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or type(size) is not int
            or size < 0
        ):
            _fail("provenance-pages-invalid")
        if source in provenance_index:
            _fail("provenance-pages-duplicate")
        provenance_index[source] = (digest, size)

    pages: list[MirrorPage] = []
    seen_sources: set[str] = set()
    seen_markdown: set[Path] = set()
    seen_html: set[Path] = set()
    origins: set[tuple[str, str]] = set()
    total_source_bytes = 0
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "source",
            "url",
            "canonical_url",
            "markdown_url",
            "sha256",
            "bytes",
        }:
            _fail("mirror-entry-invalid")
        source = entry.get("source")
        canonical = entry.get("canonical_url")
        url = entry.get("url")
        markdown_url = entry.get("markdown_url")
        digest = entry.get("sha256")
        size = entry.get("bytes")
        if (
            not isinstance(source, str)
            or not isinstance(canonical, str)
            or not isinstance(url, str)
            or not isinstance(markdown_url, str)
            or canonical != url
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or type(size) is not int
            or size < 0
            or size > MAX_SOURCE_BYTES
        ):
            _fail("mirror-entry-invalid")
        if source in seen_sources or source not in provenance_index:
            _fail("mirror-entry-duplicate")
        source_path = _safe_existing_path(root, source, "source")
        if site in source_path.parents or source_path == site:
            _fail("source-site-recursion")
        source_bytes = _regular_bytes(source_path, "source", MAX_SOURCE_BYTES)
        try:
            source_text = source_bytes.decode("utf-8")
        except UnicodeDecodeError:
            _fail("source-invalid-encoding")
        if DIRECTIVE_MARKER_PATTERN.search(source_text):
            _fail("source-agent-directive")
        _scan_safe_text(source_text, "source")
        if (
            len(source_bytes) != size
            or hashlib.sha256(source_bytes).hexdigest() != digest
        ):
            _fail("source-digest-stale")
        if provenance_index[source] != (digest, size):
            _fail("provenance-digest-stale")
        total_source_bytes += len(source_bytes)
        if total_source_bytes > MAX_TOTAL_SOURCE_BYTES:
            _fail("source-total-oversize")
        scheme, host, canonical_path = _public_url(canonical, "canonical")
        markdown_scheme, markdown_host, markdown_path = _public_url(
            markdown_url, "markdown"
        )
        if (scheme, host) != (markdown_scheme, markdown_host):
            _fail("mirror-origin-mismatch")
        origins.add((scheme, host))
        decoded_markdown_path = unquote(markdown_path)
        markdown_parts = [part for part in decoded_markdown_path.split("/") if part]
        if not markdown_parts or markdown_parts[-1] != "index.md":
            _fail("markdown-fallback-invalid")
        markdown_relative = PurePosixPath(*markdown_parts).as_posix()
        markdown_local = _safe_output_path(site, markdown_relative, "markdown-output")
        canonical_parts = [part for part in canonical_path.split("/") if part]
        if canonical_path.endswith("/"):
            html_parts = (*canonical_parts, "index.html")
        else:
            if not canonical_parts:
                _fail("canonical-path-invalid")
            html_name = PurePosixPath(canonical_parts[-1]).with_suffix(".html").name
            html_parts = (*canonical_parts[:-1], html_name)
        html_relative = PurePosixPath(*html_parts).as_posix()
        html_local = _safe_output_path(site, html_relative, "html-output")
        if markdown_local in seen_markdown or html_local in seen_html:
            _fail("mirror-output-duplicate")
        _regular_bytes(html_local, "html-output", MAX_HTML_BYTES)
        seen_sources.add(source)
        seen_markdown.add(markdown_local)
        seen_html.add(html_local)
        pages.append(
            MirrorPage(
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
        )
    if len(origins) != 1:
        _fail("mirror-origin-mismatch")
    if set(provenance_index) != seen_sources:
        _fail("provenance-pages-incomplete")
    return tuple(pages)


def _html_state(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        _fail("html-invalid-encoding")
    for tag in META_TAG_PATTERN.findall(text):
        attributes = {
            match.group("name").lower(): match.group("value")
            for match in ATTRIBUTE_PATTERN.finditer(tag)
        }
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
        attributes = {
            match.group("name").lower(): match.group("value")
            for match in ATTRIBUTE_PATTERN.finditer(tag)
        }
        if (
            attributes.get("rel", "").lower() == "alternate"
            and attributes.get("type", "").lower() == "text/markdown"
        ):
            href = attributes.get("href")
            if href is None:
                _fail("html-alternate-invalid")
            hrefs.append(href)
    return hrefs


def _html_with_alternate(
    page: MirrorPage, payload: bytes, llms_url: str
) -> tuple[bytes, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        _fail("html-invalid-encoding")
    matches = _markdown_alternate_hrefs(text)
    expected = html.escape(page.markdown_url, quote=True)
    if matches and any(
        value != page.markdown_url and value != expected for value in matches
    ):
        _fail("html-alternate-conflict")
    has_alternate = page.markdown_url in matches or expected in matches

    directive_matches = list(DIRECTIVE_PATTERN.finditer(text))
    if DIRECTIVE_MARKER_PATTERN.search(text):
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
        has_directive = True
    else:
        has_directive = False

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


def _common_site_base(pages: Iterable[MirrorPage]) -> str:
    paths = [urlsplit(page.canonical_url).path for page in pages]
    segments = [tuple(part for part in path.split("/") if part) for path in paths]
    if not segments:
        _fail("mirror-entries-invalid")
    prefix = list(segments[0])
    for current in segments[1:]:
        length = 0
        for left, right in zip(prefix, current):
            if left != right:
                break
            length += 1
        prefix = prefix[:length]
    return "/" + "/".join(prefix) + ("/" if prefix else "")


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
    sitemap_indexes: list[int] = []
    for index, line in enumerate(lines):
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
        sitemap_indexes.append(index)
    if len(sitemap_indexes) > 1:
        _fail("robots-sitemap-duplicate")
    if sitemap_indexes:
        lines[sitemap_indexes[0]] = sitemap_line
        return "".join(lines).encode("utf-8")
    separator = "" if not text or text.endswith(("\n", "\r")) else "\n"
    return (text + separator + sitemap_line).encode("utf-8")


def _derived_assets(
    pages: tuple[MirrorPage, ...], site: Path
) -> tuple[tuple[Path, bytes], ...]:
    first = urlsplit(pages[0].canonical_url)
    base = _common_site_base(pages)
    sitemap_url = urlunsplit((first.scheme, first.netloc, f"{base}sitemap.xml", "", ""))
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


def _prepare(
    root: Path,
    site: Path,
    *,
    readiness_input_path: Path,
    schema_path: Path,
    readiness_manifest_path: Path,
    mirror_manifest_path: Path,
) -> DeliveryPlan:
    schema = _read_json(schema_path, "schema")
    readiness_input = _read_json(readiness_input_path, "readiness-input")
    normalized_input = _validate_readiness_input(readiness_input, schema)
    _validate_capability_paths(root, readiness_input)
    if normalized_input["content_signals"]["policy"] not in SIGNAL_POLICIES:
        _fail("content-signals-policy-required")
    readiness_manifest = _read_json(readiness_manifest_path, "readiness-manifest")
    if readiness_manifest.get("schema_version") != SCHEMA_VERSION:
        _fail("readiness-manifest-stale")
    if not isinstance(readiness_manifest.get("generator_version"), str):
        _fail("readiness-manifest-invalid")
    _scan_safe_text(readiness_manifest, "readiness-manifest")
    for field in ("project", "applicability", "standards", "capabilities"):
        if readiness_manifest.get(field) != readiness_input.get(field):
            _fail("readiness-manifest-stale")
    if readiness_manifest.get("content_signals") != normalized_input["content_signals"]:
        _fail("content-signals-stale")
    manifest_budgets = readiness_manifest.get("budgets")
    if not isinstance(manifest_budgets, Mapping):
        _fail("readiness-manifest-invalid")
    for field in ("curated_chars", "summary_chars", "full_chars"):
        if manifest_budgets.get(field) != readiness_input["budgets"].get(field):
            _fail("readiness-manifest-stale")
    capabilities = readiness_manifest.get("capabilities")
    if not isinstance(capabilities, Mapping) or set(capabilities) != CAPABILITY_KEYS:
        _fail("readiness-capabilities-invalid")
    _scan_safe_text(capabilities, "readiness-capabilities")
    generated_outputs = _validate_generated_outputs(root, readiness_manifest)
    mirror_manifest = _read_json(mirror_manifest_path, "mirror-manifest")
    pages = _source_manifest_pages(root, site, mirror_manifest, readiness_manifest)

    mirrors = tuple((page.markdown_path, page.source_bytes) for page in pages)
    first = urlsplit(pages[0].canonical_url)
    base = _common_site_base(pages)
    llms_url = urlunsplit((first.scheme, first.netloc, f"{base}llms.txt", "", ""))
    _public_url(llms_url, "llms")
    html_outputs: list[tuple[Path, bytes]] = []
    for page in pages:
        payload = _regular_bytes(page.html_path, "html-output", MAX_HTML_BYTES)
        updated, _ = _html_with_alternate(page, payload, llms_url)
        html_outputs.append((page.html_path, updated))

    # Derived robots/sitemap/nojekyll assets are planned only after every source
    # digest, fallback path, and HTML target has passed the mirror gate.
    generated_assets = tuple(
        (
            _safe_output_path(site, relative, "generated-site-output"),
            payload,
        )
        for relative, payload in generated_outputs
    )
    assets = generated_assets + _derived_assets(pages, site)
    manifest_digest = hashlib.sha256(
        json.dumps(readiness_manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return DeliveryPlan(
        pages=pages,
        mirrors=mirrors,
        html=tuple(html_outputs),
        assets=assets,
        manifest_digest=manifest_digest,
    )


def _assert_current(plan: DeliveryPlan) -> None:
    for path, expected in (*plan.mirrors, *plan.html, *plan.assets):
        actual = _regular_bytes(
            path, "delivery-output", max(MAX_HTML_BYTES, len(expected))
        )
        if actual != expected:
            _fail("delivery-not-current")


def _apply(plan: DeliveryPlan) -> None:
    for page in plan.pages:
        if (
            _regular_bytes(page.source_path, "source", MAX_SOURCE_BYTES)
            != page.source_bytes
        ):
            _fail("source-digest-stale")
    for path, payload in plan.mirrors:
        _atomic_write(path, payload, "markdown-output")
    # HTML alternates and derived assets are deliberately written only after
    # every source-derived mirror exists and has the declared digest.
    for path, expected in plan.mirrors:
        if _regular_bytes(path, "markdown-output", MAX_SOURCE_BYTES) != expected:
            _fail("markdown-output-mismatch")
    for path, payload in plan.html:
        _atomic_write(path, payload, "html-output")
    for path, payload in plan.assets:
        _atomic_write(path, payload, "derived-asset")


def build(
    root: str | Path = ".",
    site: str | Path = "site",
    *,
    readiness_input: str = "docs/agent-readiness.json",
    schema: str = "docs/agent-readiness.schema.json",
    readiness_manifest: str = "agent-readiness-manifest.json",
    mirror_manifest: str = "markdown-mirror-manifest.json",
    check: bool = False,
) -> dict[str, Any]:
    """Build or verify Pages delivery from canonical readiness artifacts."""

    workspace = _safe_root(root)
    site_root = _safe_site(workspace, site)
    if not site_root.is_dir() or site_root.is_symlink():
        _fail("site-invalid")
    plan = _prepare(
        workspace,
        site_root,
        readiness_input_path=_safe_existing_path(
            workspace, readiness_input, "readiness-input"
        ),
        schema_path=_safe_existing_path(workspace, schema, "schema"),
        readiness_manifest_path=_safe_existing_path(
            workspace, readiness_manifest, "readiness-manifest"
        ),
        mirror_manifest_path=_safe_existing_path(
            workspace, mirror_manifest, "mirror-manifest"
        ),
    )
    if check:
        _assert_current(plan)
    else:
        _apply(plan)
        _assert_current(plan)
    return {
        "ok": True,
        "checker_version": CHECKER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "mirror_contract": MIRROR_CONTRACT,
        "entries": len(plan.pages),
        "mirrors": len(plan.mirrors),
        "derived_assets": len(plan.assets),
        "manifest_digest": plan.manifest_digest,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "check", "tck"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--root", default=".")
        subparser.add_argument("--site", default="site")
        subparser.add_argument("--readiness-input", default="docs/agent-readiness.json")
        subparser.add_argument("--schema", default="docs/agent-readiness.schema.json")
        subparser.add_argument(
            "--readiness-manifest", default="agent-readiness-manifest.json"
        )
        subparser.add_argument(
            "--mirror-manifest", default="markdown-mirror-manifest.json"
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = build(
            args.root,
            args.site,
            readiness_input=args.readiness_input,
            schema=args.schema,
            readiness_manifest=args.readiness_manifest,
            mirror_manifest=args.mirror_manifest,
            check=args.command in {"check", "tck"},
        )
    except ReadinessTckError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "checker_version": CHECKER_VERSION,
                    "schema_version": SCHEMA_VERSION,
                    "mirror_contract": MIRROR_CONTRACT,
                    "error_code": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
