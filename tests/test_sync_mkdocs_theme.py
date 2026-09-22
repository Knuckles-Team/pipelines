"""Shared MkDocs theme assets stay byte-identical and accessible."""

from __future__ import annotations

from pathlib import Path
import sys
from xml.etree import ElementTree

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sync_mkdocs_theme import ThemeSyncError, sync_theme


ROOT = Path(__file__).parents[1]
SVG_NS = "{http://www.w3.org/2000/svg}"


def test_sync_then_check_is_byte_identical_and_detects_drift(tmp_path: Path) -> None:
    assert sync_theme(
        source_root=ROOT,
        repository_root=tmp_path,
        content_source="docs",
        mode="sync",
    ) == []
    assert sync_theme(
        source_root=ROOT,
        repository_root=tmp_path,
        content_source="docs",
        mode="check",
    ) == []

    generated = tmp_path / "docs/stylesheets/extra.css"
    generated.write_text("/* local drift */\n", encoding="utf-8")
    assert sync_theme(
        source_root=ROOT,
        repository_root=tmp_path,
        content_source="docs",
        mode="check",
    ) == ["generated file differs: docs/stylesheets/extra.css"]


def test_sync_rejects_path_escape_and_check_does_not_create_files(tmp_path: Path) -> None:
    with pytest.raises(ThemeSyncError, match="contained relative path"):
        sync_theme(
            source_root=ROOT,
            repository_root=tmp_path,
            content_source="../outside",
            mode="sync",
        )

    assert sync_theme(
        source_root=ROOT,
        repository_root=tmp_path,
        content_source="pages",
        mode="check",
    )
    assert not (tmp_path / "pages").exists()


def test_theme_components_use_accessible_native_controls() -> None:
    template = (ROOT / "templates/mkdocs-theme/overrides/main.html").read_text(encoding="utf-8")
    css = (ROOT / "templates/mkdocs-theme/extra.css").read_text(encoding="utf-8")

    assert "<details class=\"site-switcher\">" in template
    assert 'aria-label="Choose an ecosystem documentation site"' in template
    assert 'aria-current="page"' in template
    assert "<script" not in template.lower()
    assert ":focus-visible" in css
    assert "prefers-reduced-motion: reduce" in css
    assert css.count("{") == css.count("}")


def test_runtime_svg_is_accessible_and_has_all_entrypoint_flows() -> None:
    diagram = ROOT / "templates/mkdocs-theme/assets/runtime-architecture.svg"
    svg_root = ElementTree.parse(diagram).getroot()
    flows = svg_root.find(f".//{SVG_NS}g[@class='arrow']")
    text = " ".join(element.text or "" for element in svg_root.iter(f"{SVG_NS}text"))
    mermaid = diagram.with_suffix(".mmd").read_text(encoding="utf-8")

    assert svg_root.attrib["role"] == "img"
    assert svg_root.find(f"{SVG_NS}title") is not None
    assert svg_root.find(f"{SVG_NS}desc") is not None
    assert flows is not None and len(list(flows)) == 13
    for label in (
        "Agent Web UI",
        "browser experience",
        "Agent Terminal UI",
        "Geniusbot",
        "Messaging",
        "Graph OS",
        "governed runtime gateway",
        "Agent Utilities",
        "agent control plane",
        "Epistemic Graph",
        "Agent Connector SDK",
        "typed source integration",
    ):
        assert label in text
        assert label.split()[0] in mermaid
