"""Validation for capability artifacts and their source evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .constants import MAX_SOURCE_BYTES, OAUTH_METADATA_FIELDS
from .errors import _fail
from .filesystem import (
    _read_json,
    _regular_bytes,
    _safe_existing_dir,
    _safe_existing_path,
)
from .privacy import _scan_safe_text


_ARTIFACT_METADATA_KEYS = {
    "applicable",
    "surface",
    "source",
    "version",
    "http_transport",
}


def _skill_document_exists(skills_root: Path) -> bool:
    """Return whether one immediate skill directory contains ``SKILL.md``."""

    for entry in skills_root.iterdir():
        if not entry.is_dir() or entry.is_symlink():
            continue
        skill_file = entry / "SKILL.md"
        if skill_file.is_file() and not skill_file.is_symlink():
            return True
    return False


def _validate_skills_path(root: Path, raw: Mapping[str, Any]) -> None:
    """Prove that an applicable skills capability has a usable skill tree."""

    skills_root = _safe_existing_dir(root, raw.get("path"), "skills-path")
    if not _skill_document_exists(skills_root):
        _fail("skills-path-not-proven")


def _validate_oauth_metadata(root: Path, raw: Mapping[str, Any]) -> None:
    """Read each declared OAuth metadata document before its artifact."""

    for field in OAUTH_METADATA_FIELDS:
        if field in raw:
            _read_json(
                _safe_existing_path(root, raw[field], f"{field}-metadata"),
                f"{field}-metadata",
            )


def _read_capability_artifact(
    root: Path, name: str, raw: Mapping[str, Any]
) -> dict[str, Any]:
    """Read the capability artifact named by an applicable declaration."""

    artifact = _safe_existing_path(root, raw.get("artifact"), f"{name}-artifact")
    return _read_json(artifact, f"{name}-artifact")


def _validate_artifact_shape(name: str, metadata: Mapping[str, Any]) -> None:
    """Validate the artifact's fields and surface identity."""

    if set(metadata) - _ARTIFACT_METADATA_KEYS:
        _fail("capability-artifact-schema-invalid")
    if "http_transport" in metadata and (
        name != "mcp" or type(metadata["http_transport"]) is not bool
    ):
        _fail("capability-artifact-schema-invalid")
    if metadata.get("applicable") is not True or metadata.get("surface") != name:
        _fail("capability-artifact-unproven")


def _validate_mcp_transport(
    name: str, raw: Mapping[str, Any], metadata: Mapping[str, Any]
) -> None:
    """Require explicit HTTP transport proof for networked MCP surfaces."""

    if (
        name == "mcp"
        and raw.get("transport") in {"streamable-http", "sse"}
        and metadata.get("http_transport") is not True
    ):
        _fail("mcp-transport-not-proven")


def _validate_artifact_metadata(
    name: str, raw: Mapping[str, Any], metadata: Mapping[str, Any]
) -> str:
    """Validate artifact identity and transport evidence."""

    _validate_artifact_shape(name, metadata)
    _validate_mcp_transport(name, raw, metadata)
    source = metadata.get("source")
    if not isinstance(source, str):
        _fail("capability-artifact-source-invalid")
    return source


def _validate_artifact_source(
    root: Path,
    name: str,
    *,
    source: str,
    metadata: Mapping[str, Any],
) -> None:
    """Prove and privacy-scan the source named by a capability artifact."""

    _regular_bytes(
        _safe_existing_path(root, source, f"{name}-artifact-source"),
        f"{name}-artifact-source",
        MAX_SOURCE_BYTES,
    )
    _scan_safe_text(metadata, f"{name}-artifact")


def _validate_capability_artifact(
    root: Path, name: str, raw: Mapping[str, Any]
) -> None:
    """Validate one non-skills capability artifact and its source."""

    _validate_oauth_metadata(root, raw)
    metadata = _read_capability_artifact(root, name, raw)
    source = _validate_artifact_metadata(name, raw, metadata)
    _validate_artifact_source(root, name, source=source, metadata=metadata)


def _validate_capability_paths(root: Path, value: Mapping[str, Any]) -> None:
    """Prove the filesystem evidence for every applicable capability."""

    capabilities = value.get("capabilities")
    if not isinstance(capabilities, Mapping):
        _fail("capabilities-invalid")
    for name, raw in capabilities.items():
        if not isinstance(raw, Mapping) or raw.get("applicable") is not True:
            continue
        if name == "skills":
            _validate_skills_path(root, raw)
            continue
        _validate_capability_artifact(root, name, raw)
