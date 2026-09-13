"""Plan, apply, and verify deterministic Pages readiness delivery."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import constants
from .declaration import _validate_readiness_input, normalized_capabilities
from .errors import _fail
from .evidence import _validate_capability_paths
from .filesystem import (
    _atomic_write,
    _read_json,
    _regular_bytes,
    _safe_existing_path,
    _safe_output_path,
    _safe_root,
    _safe_site,
)
from .generated import _validate_generated_outputs
from .html_assets import _derived_assets, _html_with_alternate
from .mirrors import _source_manifest_pages
from .mkdocs import mkdocs_site_url
from .models import DeliveryPlan, MirrorPage
from .privacy import _scan_safe_text
from .urls import _site_asset_url


def _validate_manifest_identity(
    manifest: Mapping[str, Any], readiness_input: Mapping[str, Any]
) -> None:
    if manifest.get("schema_version") != constants.SCHEMA_VERSION:
        _fail("readiness-manifest-stale")
    if not isinstance(manifest.get("generator_version"), str):
        _fail("readiness-manifest-invalid")
    _scan_safe_text(manifest, "readiness-manifest")
    for field in ("project", "applicability", "standards"):
        if manifest.get(field) != readiness_input.get(field):
            _fail("readiness-manifest-stale")


def _validate_manifest_projection(
    manifest: Mapping[str, Any],
    readiness_input: Mapping[str, Any],
    normalized_input: Mapping[str, Any],
) -> None:
    if manifest.get("capabilities") != normalized_capabilities(
        readiness_input["capabilities"]
    ):
        _fail("readiness-manifest-stale")
    if manifest.get("content_signals") != normalized_input["content_signals"]:
        _fail("content-signals-stale")


def _validate_manifest_budgets(
    manifest: Mapping[str, Any], readiness_input: Mapping[str, Any]
) -> None:
    budgets = manifest.get("budgets")
    if not isinstance(budgets, Mapping):
        _fail("readiness-manifest-invalid")
    for field in ("curated_chars", "summary_chars", "full_chars"):
        if budgets.get(field) != readiness_input["budgets"].get(field):
            _fail("readiness-manifest-stale")
    capabilities = manifest.get("capabilities")
    if (
        not isinstance(capabilities, Mapping)
        or set(capabilities) != constants.CAPABILITY_KEYS
    ):
        _fail("readiness-capabilities-invalid")
    _scan_safe_text(capabilities, "readiness-capabilities")


def _validated_manifest(
    path: Path,
    readiness_input: Mapping[str, Any],
    normalized_input: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = _read_json(path, "readiness-manifest")
    _validate_manifest_identity(manifest, readiness_input)
    _validate_manifest_projection(manifest, readiness_input, normalized_input)
    _validate_manifest_budgets(manifest, readiness_input)
    return manifest


def _html_outputs(
    pages: tuple[MirrorPage, ...], site_url: str
) -> tuple[tuple[Path, bytes], ...]:
    llms_url = _site_asset_url(site_url, "llms.txt")
    outputs: list[tuple[Path, bytes]] = []
    for page in pages:
        payload = _regular_bytes(
            page.html_path, "html-output", constants.MAX_HTML_BYTES
        )
        updated, _ = _html_with_alternate(page, payload, llms_url)
        outputs.append((page.html_path, updated))
    return tuple(outputs)


def _generated_assets(
    site: Path, generated: tuple[tuple[str, bytes], ...]
) -> tuple[tuple[Path, bytes], ...]:
    return tuple(
        (_safe_output_path(site, relative, "generated-site-output"), payload)
        for relative, payload in generated
    )


def _prepare(
    root: Path,
    site: Path,
    *,
    site_url: str,
    readiness_input_path: Path,
    schema_path: Path,
    readiness_manifest_path: Path,
    mirror_manifest_path: Path,
) -> DeliveryPlan:
    schema = _read_json(schema_path, "schema")
    readiness_input = _read_json(readiness_input_path, "readiness-input")
    normalized_input = _validate_readiness_input(readiness_input, schema)
    _validate_capability_paths(root, readiness_input)
    if (
        normalized_input["content_signals"]["policy"]
        not in constants.SIGNAL_POLICIES
    ):
        _fail("content-signals-policy-required")
    readiness_manifest = _validated_manifest(
        readiness_manifest_path, readiness_input, normalized_input
    )
    generated = _validate_generated_outputs(root, readiness_manifest, readiness_input)
    mirror_manifest = _read_json(mirror_manifest_path, "mirror-manifest")
    pages = _source_manifest_pages(
        root,
        site,
        site_url,
        mirror_manifest=mirror_manifest,
        readiness_manifest=readiness_manifest,
    )
    mirrors = tuple((page.markdown_path, page.source_bytes) for page in pages)
    html = _html_outputs(pages, site_url)
    assets = _generated_assets(site, generated) + _derived_assets(pages, site, site_url)
    digest = hashlib.sha256(
        json.dumps(readiness_manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return DeliveryPlan(pages, mirrors, html, assets, digest)


def _assert_current(plan: DeliveryPlan) -> None:
    for path, expected in (*plan.mirrors, *plan.html, *plan.assets):
        actual = _regular_bytes(
            path,
            "delivery-output",
            max(constants.MAX_HTML_BYTES, len(expected)),
        )
        if actual != expected:
            _fail("delivery-not-current")


def _apply(plan: DeliveryPlan) -> None:
    for page in plan.pages:
        actual = _regular_bytes(
            page.source_path, "source", constants.MAX_SOURCE_BYTES
        )
        if actual != page.source_bytes:
            _fail("source-digest-stale")
    for path, payload in plan.mirrors:
        _atomic_write(path, payload, "markdown-output")
    for path, expected in plan.mirrors:
        actual = _regular_bytes(
            path, "markdown-output", constants.MAX_SOURCE_BYTES
        )
        if actual != expected:
            _fail("markdown-output-mismatch")
    for path, payload in plan.html:
        _atomic_write(path, payload, "html-output")
    for path, payload in plan.assets:
        _atomic_write(path, payload, "derived-asset")


def build(
    root: str | Path = ".",
    site: str | Path = "site",
    *,
    content_source: str = "pages",
    readiness_input: str | None = None,
    schema: str | None = None,
    readiness_manifest: str = "agent-readiness-manifest.json",
    mirror_manifest: str = "markdown-mirror-manifest.json",
    check: bool = False,
) -> dict[str, Any]:
    """Build or verify Pages delivery from canonical readiness artifacts."""

    input_path = readiness_input or f"{content_source}/agent-readiness.json"
    schema_path = schema or f"{content_source}/agent-readiness.schema.json"
    workspace = _safe_root(root)
    site_root = _safe_site(workspace, site)
    if not site_root.is_dir() or site_root.is_symlink():
        _fail("site-invalid")
    plan = _prepare(
        workspace,
        site_root,
        site_url=mkdocs_site_url(workspace),
        readiness_input_path=_safe_existing_path(
            workspace, input_path, "readiness-input"
        ),
        schema_path=_safe_existing_path(workspace, schema_path, "schema"),
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
        "checker_version": constants.CHECKER_VERSION,
        "schema_version": constants.SCHEMA_VERSION,
        "mirror_contract": constants.MIRROR_CONTRACT,
        "entries": len(plan.pages),
        "mirrors": len(plan.mirrors),
        "derived_assets": len(plan.assets),
        "manifest_digest": plan.manifest_digest,
    }
