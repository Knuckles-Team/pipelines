"""Immutable data models shared by the Pages readiness contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
