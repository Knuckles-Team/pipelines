"""Shared MkDocs theme assets stay byte-identical and accessible."""

from __future__ import annotations

from pathlib import Path
import sys
from xml.etree import ElementTree

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sync_mkdocs_theme import THEME_FILES, ThemeSyncError, sync_theme


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
    flows = svg_root.find(f".//{SVG_NS}g[@class='connections']")
    marker = svg_root.find(f".//{SVG_NS}marker[@id='arrow']")
    background = svg_root.find(f"{SVG_NS}rect[@class='bg']")
    text = " ".join(element.text or "" for element in svg_root.iter(f"{SVG_NS}text"))
    mermaid = diagram.with_suffix(".mmd").read_text(encoding="utf-8")

    assert svg_root.attrib["role"] == "img"
    assert svg_root.find(f"{SVG_NS}title") is not None
    assert svg_root.find(f"{SVG_NS}desc") is not None
    assert background is not None and background.attrib["fill"] == "none"
    styles = " ".join(element.text or "" for element in svg_root.iter(f"{SVG_NS}style"))
    assert "prefers-color-scheme: light" in styles
    assert "prefers-color-scheme: dark" in styles
    marker = svg_root.find(f".//{SVG_NS}marker[@id='arrow']")
    assert marker is not None and marker.attrib["refX"] == "10"
    assert flows is not None and len(list(flows)) == 10
    assert list(svg_root).index(flows) == len(list(svg_root)) - 1
    path_values = [path.attrib["d"] for path in flows]
    expected_connectors = {
        "M60 90L120 135": ((60, 90), (120, 135)),
        "M100 90L310 135": ((100, 90), (310, 135)),
        "M140 90L500 135": ((140, 90), (500, 135)),
        "M180 90L692 135": ((180, 90), (692, 135)),
        "M780 180H825": ((780, 180), (825, 180)),
        "M780 285H825": ((780, 285), (825, 285)),
        "M1050 305V335": ((1050, 305), (1050, 335)),
        "M1050 435V485": ((1050, 435), (1050, 485)),
        "M255 590H445": ((255, 590), (445, 590)),
        "M705 590H825": ((705, 590), (825, 590)),
    }
    assert path_values == list(expected_connectors)
    assert marker is not None and marker.attrib["refX"] == "10"
    assert all(path.attrib.get("class") == "arrow" for path in flows)
    boxes = (
        (35, 35, 205, 90),
        (35, 135, 205, 225),
        (225, 135, 395, 225),
        (415, 135, 585, 225),
        (605, 135, 780, 225),
        (415, 245, 780, 325),
        (825, 145, 1275, 305),
        (825, 335, 1275, 435),
        (825, 485, 1275, 610),
        (35, 545, 255, 635),
        (445, 545, 705, 635),
    )
    rectangles = list(svg_root.iter(f"{SVG_NS}rect"))
    mcp_box = next(
        rect
        for rect in rectangles
        if rect.attrib.get("x") == "415" and rect.attrib.get("y") == "245"
    )
    assert mcp_box.attrib["width"] == "365"
    assert int(mcp_box.attrib["x"]) + int(mcp_box.attrib["width"]) == 780

    def is_box_border(point: tuple[int, int], bounds: tuple[int, int, int, int]) -> bool:
        x, y = point
        left, top, right, bottom = bounds
        return (x in (left, right) and top <= y <= bottom) or (
            y in (top, bottom) and left <= x <= right
        )

    for start, end in expected_connectors.values():
        assert any(is_box_border(start, box) for box in boxes)
        assert any(is_box_border(end, box) for box in boxes)
    assert not {
        "M210 180H825",
        "M400 180H825",
        "M590 180H825",
        "M610 285H825",
        "M805 285H825",
        "M705 590H845",
        "M705 590H825V548",
    }.intersection(path_values)
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
    for edge in (
        "WebUI --> GraphOS",
        "TUI -->|REST| GraphOS",
        "GraphOS --> AU",
        "AU --> EG",
        "Sources --> SDK",
        "SDK --> EG",
    ):
        assert edge in mermaid


def test_all_seven_product_logo_assets_remain_canonical() -> None:
    logos = ROOT / "templates/mkdocs-theme/assets/brands"
    expected = {
        "agent-terminal-ui-logo-v1.png",
        "agent-connector-sdk-logo-v1.png",
        "epistemic-graph-logo-v1.png",
        "agent-webui-logo-v1.png",
        "geniusbot-logo-v1.png",
        "graph-os-logo-v1.png",
        "agent-utilities-logo-v1.png",
    }

    expected_sources = {f"assets/brands/{name}" for name in expected}
    configured_sources = {
        item.source for item in THEME_FILES if item.source.startswith("assets/brands/")
    }

    assert {path.name for path in logos.glob("*.png")} == expected
    assert configured_sources == expected_sources
    for name in expected:
        assert (logos / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
