"""Path-shape validation for generated Pages readiness artifacts."""

from __future__ import annotations

from pathlib import PurePosixPath

from .constants import GENERATOR_OUTPUTS, WELL_KNOWN_OUTPUTS
from .errors import _fail
from .filesystem import _path_parts


def _validate_generated_path(raw: object) -> str:
    """Validate one path against the generator's output contract."""

    if not isinstance(raw, str) or "\\" in raw:
        _fail("generated-path-invalid")
    parts = _path_parts(raw, "generated")
    _validate_generated_parts(parts)
    return PurePosixPath(*parts).as_posix()


def _validate_well_known_parts(parts: tuple[str, ...]) -> None:
    """Validate a generated ``.well-known`` leaf."""

    if len(parts) != 2 or parts[1] not in WELL_KNOWN_OUTPUTS:
        _fail("generated-path-outside-contract")


def _validate_sections_parts(parts: tuple[str, ...]) -> None:
    """Validate a generated ``llms-sections`` fallback."""

    if len(parts) < 2 or parts[-1] != "llms.txt":
        _fail("generated-path-invalid")


def _validate_generated_parts(parts: tuple[str, ...]) -> None:
    """Validate the contract-specific shape of normalized path parts."""

    if parts[0] not in GENERATOR_OUTPUTS:
        _fail("generated-path-outside-contract")
    if parts[0] == ".well-known":
        _validate_well_known_parts(parts)
    elif parts[0] != "llms-sections" and len(parts) != 1:
        _fail("generated-path-invalid")
    if parts[0] == "llms-sections":
        _validate_sections_parts(parts)


def _validate_generated_list(generated: object) -> list[str]:
    """Normalize and validate a manifest's generated path list."""

    if not isinstance(generated, list) or not generated or len(generated) > 256:
        _fail("generated-list-invalid")
    normalized = [_validate_generated_path(raw) for raw in generated]
    if len(set(normalized)) != len(normalized):
        _fail("generated-path-duplicate")
    required = {"llms.txt", "markdown-mirror-manifest.json"}
    if not required.issubset(normalized):
        _fail("generated-output-missing")
    if "agent-readiness-manifest.json" in normalized:
        _fail("generated-path-invalid")
    return normalized
