"""Spec delivery is a native, flag-gated menu entry in the shared theme."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scripts.sync_mkdocs_theme import sync_theme
from skill_graph.model import REPOS

THEME = ROOT / "templates/mkdocs-theme"
MAIN = (THEME / "overrides/main.html").read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-PAGES-R018.1")
def test_flag_is_env_driven() -> None:
    base = (THEME / "base.mkdocs.yml").read_text(encoding="utf-8")
    assert "spec_delivery: !ENV [SPEC_DELIVERY_ENABLED, false]" in base
    workflow = (ROOT / ".github/workflows/pages_pipeline.yml").read_text(encoding="utf-8")
    assert "SPEC_DELIVERY_ENABLED: ${{ inputs.spec_dashboard_enabled }}" in workflow


@pytest.mark.spec("PIPE-PAGES-R018.2")
def test_entry_is_root_relative_and_flag_gated() -> None:
    assert "{% if config.extra.spec_delivery %}" in MAIN
    assert 'href="{{ base_url }}/spec-delivery/"' in MAIN
    assert "github.io" not in MAIN


@pytest.mark.spec("PIPE-PAGES-R018.3")
def test_menu_iterates_the_single_site_list() -> None:
    assert "for site in config.extra.ecosystem.sites" in MAIN
    assert "<details" in MAIN and "<script" not in MAIN


@pytest.mark.spec("PIPE-PAGES-R018.4")
def test_site_urls_match_repos() -> None:
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!ENV", lambda loader, node: None)
    base = yaml.load((THEME / "base.mkdocs.yml").read_text(encoding="utf-8"), Loader)
    for site in base["extra"]["ecosystem"]["sites"]:
        if site["slug"] in REPOS:
            assert site["url"] == REPOS[site["slug"]][1]


@pytest.mark.spec("PIPE-PAGES-R018.5")
def test_theme_sync_check_passes_with_entry(tmp_path: Path) -> None:
    for mode in ("sync", "check"):
        assert sync_theme(source_root=ROOT, repository_root=tmp_path, content_source="docs", mode=mode) == []
    assert "focus-visible" in MAIN and "<style>" in MAIN
    assert "site-spec-delivery" not in (THEME / "extra.css").read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-PAGES-R042")
def test_architecture_explorer_link_opens_the_current_repository_node() -> None:
    base = (THEME / "base.mkdocs.yml").read_text(encoding="utf-8")
    assert "architecture_explorer: !ENV [ARCHITECTURE_EXPLORER_ENABLED, false]" in base
    assert "{% if config.extra.architecture_explorer %}" in MAIN
    assert 'href="{{ base_url }}/architecture/' in MAIN
    assert "config.extra.architecture_nodes[config.extra.ecosystem.current]" in MAIN
