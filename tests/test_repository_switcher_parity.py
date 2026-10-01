"""The shared theme's repository switcher stays in sync with the declared core repos.

PIPE-PAGES-R001: the documentation site's repository switcher is renamed and
its repository list is completed to match the full declared set of core
repositories, replacing any per-repository duplicate copies.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.skill_graph.model import REPOS

ROOT = Path(__file__).resolve().parents[1]
BASE_MKDOCS = ROOT / "templates" / "mkdocs-theme" / "base.mkdocs.yml"
MAIN_HTML = ROOT / "templates" / "mkdocs-theme" / "overrides" / "main.html"
EXTRA_CSS = ROOT / "templates" / "mkdocs-theme" / "extra.css"

# The switcher lists every repo the skill-graph corpus declares as core, plus
# pipelines itself (the shared-theme source, which does not list itself in
# ``REPOS`` since that registry only names skill-graph extraction targets).
DECLARED_CORE_REPOSITORIES = frozenset(REPOS) | {"pipelines"}


def _ecosystem_sites() -> list[dict]:
    document = yaml.safe_load(BASE_MKDOCS.read_text(encoding="utf-8"))
    return document["extra"]["ecosystem"]["sites"]


def test_switcher_repository_list_matches_the_declared_core_repository_set() -> None:
    sites = _ecosystem_sites()
    slugs = [site["slug"] for site in sites]
    assert len(slugs) == len(set(slugs)), "duplicate switcher entry"
    assert set(slugs) == DECLARED_CORE_REPOSITORIES


def test_every_switcher_entry_has_a_name_role_url_and_repository() -> None:
    for site in _ecosystem_sites():
        assert site["name"]
        assert site["role"]
        assert site["url"].startswith("https://")
        assert site["repository"].startswith("https://github.com/Knuckles-Team/")


def test_switcher_is_named_as_a_repository_switcher_not_a_site_switcher() -> None:
    html = MAIN_HTML.read_text(encoding="utf-8")
    css = EXTRA_CSS.read_text(encoding="utf-8")
    assert "repository-switcher" in html
    assert "repository-switcher" in css
    assert "site-switcher" not in html
    assert "site-switcher" not in css


def test_generated_copies_stay_byte_identical_to_the_canonical_switcher(tmp_path: Path) -> None:
    from scripts.sync_mkdocs_theme import sync_theme

    assert sync_theme(source_root=ROOT, repository_root=tmp_path, content_source="pages", mode="sync") == []
    assert sync_theme(source_root=ROOT, repository_root=tmp_path, content_source="pages", mode="check") == []
