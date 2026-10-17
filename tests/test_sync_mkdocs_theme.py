"""Shared MkDocs theme assets stay byte-identical and accessible."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sync_mkdocs_theme import RUNTIME_DIAGRAM_URL, THEME_FILES, ThemeSyncError, sync_theme


ROOT = Path(__file__).parents[1]


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


def test_all_seven_product_logo_assets_remain_canonical() -> None:
    logos = ROOT / "templates/mkdocs-theme/assets/brands"
    expected = {
        "agent-terminal-ui-logo-v1.png",
        "agent-connector-sdk-logo-v1.png",
        "epistemic-graph-logo-v1.png",
        "agent-webui-logo-v1.png",
        "geniusbot-logo-v1.png",
        "arbora-logo-v1.png",
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


def test_theme_override_is_served_from_the_theme_checkout() -> None:
    base = (ROOT / "templates/mkdocs-theme/base.mkdocs.yml").read_text(encoding="utf-8")
    custom_dirs = [line.split(":", 1)[1].strip() for line in base.splitlines() if line.strip().startswith("custom_dir:")]
    assert custom_dirs == [".pipeline-theme/templates/mkdocs-theme/overrides"]
    assert not [item for item in THEME_FILES if item.source.startswith("overrides/")]


def test_runtime_diagram_is_not_a_theme_asset() -> None:
    assert not [item for item in THEME_FILES if "runtime-architecture" in item.source]
    assert not list((ROOT / "templates/mkdocs-theme/assets").glob("runtime-architecture.*"))


def _page(tmp_path: Path, text: str) -> Path:
    sync_theme(source_root=ROOT, repository_root=tmp_path, content_source="docs", mode="sync")
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs/index.md").write_text(text, encoding="utf-8")
    return tmp_path


def test_check_requires_no_local_runtime_diagram_copy(tmp_path: Path) -> None:
    root = _page(tmp_path, f"![Runtime]({RUNTIME_DIAGRAM_URL})\n")
    assert not (root / "docs/assets/runtime-architecture.svg").exists()
    assert sync_theme(source_root=ROOT, repository_root=root, content_source="docs", mode="check") == []


@pytest.mark.parametrize("target", ["assets/runtime-architecture.svg", "../docs/assets/runtime-architecture.svg"])
def test_check_rejects_local_runtime_diagram_references(tmp_path: Path, target: str) -> None:
    root = _page(tmp_path, f"![Runtime]({target})\n")
    assert sync_theme(source_root=ROOT, repository_root=root, content_source="docs", mode="check") == [
        f"runtime diagram must be referenced as {RUNTIME_DIAGRAM_URL}: docs/index.md"
    ]
