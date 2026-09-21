"""Repository-specific configuration for the public documentation gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.config import load_config
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.docs.public_surface_constants import (
    DISTRIBUTION_RE,
    REPOSITORY_RE,
)
from pipelines_hooks.docs.public_surface_links import public_url


@dataclass(frozen=True)
class PublicSurfaceConfig:
    """Validated repository-specific documentation identity."""

    repository: str
    distribution: str | None
    pages_url: str
    mcp_server: bool


def _required(section: object) -> dict[str, object]:
    if not isinstance(section, dict):
        raise CannotRun("[tool.pipelines_hooks.public_surface] must be a table")
    required = {"repository", "pages_url", "mcp_server"}
    missing = sorted(required - set(section))
    if missing:
        raise CannotRun(
            "[tool.pipelines_hooks.public_surface] is missing: " + ", ".join(missing)
        )
    return section


def _repository(section: dict[str, object]) -> str:
    value = section["repository"]
    if not isinstance(value, str) or not REPOSITORY_RE.fullmatch(value.strip()):
        raise CannotRun(
            "public_surface.repository must be a GitHub owner/repository identifier"
        )
    return value.strip()


def _distribution(section: dict[str, object]) -> str | None:
    value = section.get("distribution")
    if value is None:
        return None
    if not isinstance(value, str) or not DISTRIBUTION_RE.fullmatch(value.strip()):
        raise CannotRun(
            "public_surface.distribution must be a non-empty Python distribution name"
        )
    return value.strip()


def _pages_url(section: dict[str, object]) -> str:
    value = section["pages_url"]
    if not isinstance(value, str):
        raise CannotRun("public_surface.pages_url must be a public HTTPS URL")
    return public_url(value.strip(), "public_surface.pages_url")


def _mcp_server(section: dict[str, object]) -> bool:
    value = section["mcp_server"]
    if not isinstance(value, bool):
        raise CannotRun("public_surface.mcp_server must be a boolean")
    return value


def load_public_surface_config(root: Path) -> PublicSurfaceConfig:
    """Load and validate the consumer's public-surface identity."""
    section = load_config(root).section("public_surface")
    if not section:
        raise CannotRun(
            "[tool.pipelines_hooks.public_surface] is required for the public-surface gate"
        )
    values = _required(section)
    return PublicSurfaceConfig(
        repository=_repository(values),
        distribution=_distribution(values),
        pages_url=_pages_url(values),
        mcp_server=_mcp_server(values),
    )
