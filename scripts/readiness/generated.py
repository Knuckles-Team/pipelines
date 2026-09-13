"""Validation for generated Pages readiness artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .constants import (
    MAX_GENERATED_FILE_BYTES,
    MAX_TOTAL_GENERATED_BYTES,
    NON_PUBLIC_REACHABILITY,
)
from .errors import _fail
from .filesystem import _regular_bytes, _safe_existing_path
from .generated_paths import _validate_generated_list
from .privacy import _scan_safe_text


def _publicly_discoverable(raw: Mapping[str, Any]) -> bool:
    """Return whether a capability may be advertised publicly."""

    return (
        raw.get("applicable") is True
        and raw.get("reachability") not in NON_PUBLIC_REACHABILITY
    )


def _discovery_names(normalized: list[str]) -> set[str]:
    """Return the leaf names of declared ``.well-known`` outputs."""

    return {
        PurePosixPath(item).name
        for item in normalized
        if item.startswith(".well-known/")
    }


def _validate_surface_discovery(
    present: set[str],
    name: str,
    *,
    discoverable: bool,
    raw: Mapping[str, Any],
) -> None:
    """Require one public surface document only when it is declared."""

    if name not in present:
        return
    if not discoverable or not _publicly_discoverable(raw):
        _fail("generated-discovery-unbound")


def _validate_api_discovery(
    present: set[str], discoverable: bool, capabilities: Mapping[str, Any]
) -> None:
    """Require an API catalog only when a public surface is declared."""

    if "api-catalog" not in present:
        return
    public_surface = _publicly_discoverable(
        capabilities["mcp"]
    ) or _publicly_discoverable(capabilities["a2a"])
    if not discoverable or not public_surface:
        _fail("generated-discovery-unbound")


def _validate_discovery_outputs(
    normalized: list[str], readiness_input: Mapping[str, Any]
) -> None:
    """Bind generated ``.well-known`` documents to readiness declarations."""

    applicability = readiness_input["applicability"]
    capabilities = readiness_input["capabilities"]
    discoverable = applicability["discoverability"] is True
    present = _discovery_names(normalized)
    skills_expected = discoverable and capabilities["skills"]["applicable"] is True
    if ("agent-skills.json" in present) != skills_expected:
        _fail("generated-discovery-unbound")
    _validate_surface_discovery(
        present,
        "mcp-server-card.json",
        discoverable=discoverable,
        raw=capabilities["mcp"],
    )
    _validate_api_discovery(present, discoverable, capabilities)


def _validate_generated_file(root: Path, relative: str) -> bytes:
    """Read and validate one generated file."""

    path = _safe_existing_path(root, relative, "generated-output")
    payload = _regular_bytes(path, "generated-output", MAX_GENERATED_FILE_BYTES)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        _fail("generated-output-invalid-encoding")
    _scan_safe_text(text, "generated-output")
    if relative.startswith(".well-known/"):
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            _fail("generated-discovery-invalid-json")
        if not isinstance(document, dict):
            _fail("generated-discovery-invalid-json")
        _scan_safe_text(document, "generated-output")
    return payload


def _published_generated(relative: str) -> bool:
    """Return whether a generated path is copied into the Pages site."""

    return (
        relative in {"llms.txt", "llms-full.txt"}
        or relative.startswith("llms-sections/")
        or relative.startswith(".well-known/")
    )


def _validate_generated_outputs(
    root: Path, manifest: Mapping[str, Any], readiness_input: Mapping[str, Any]
) -> tuple[tuple[str, bytes], ...]:
    """Validate generated files and return the bounded published subset."""

    normalized = _validate_generated_list(manifest.get("generated"))
    _validate_discovery_outputs(normalized, readiness_input)
    total = 0
    published: list[tuple[str, bytes]] = []
    for relative in normalized:
        payload = _validate_generated_file(root, relative)
        total += len(payload)
        if _published_generated(relative):
            published.append((relative, payload))
    if total > MAX_TOTAL_GENERATED_BYTES:
        _fail("generated-output-oversize")
    return tuple(published)
