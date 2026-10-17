"""Site navigation on the spec-delivery page."""

import re

import pytest

from scripts.spec_dashboard import render
from scripts.spec_dashboard_drilldown import anchor_for, ecosystem_components


def _page():
    return render(
        {
            "repository": "Knuckles-Team/" + ecosystem_components()[0],
            "revision": "abcdef123456",
            "captured_at": "now",
            "records": [],
            "github": {},
        }
    )


def _nav(page):
    return re.search(r'<nav aria-label="Site".*?</nav>', page, re.S).group(0)


@pytest.mark.spec("PIPE-PAGES-R019.1")
def test_nav_landmark_links_documentation():
    nav = _nav(_page())
    assert nav.count('href="../"') == 2
    assert ">Documentation</a>" in nav


@pytest.mark.spec("PIPE-PAGES-R019.2")
def test_current_page_is_marked():
    nav = _nav(_page())
    assert nav.count('aria-current="page"') == 1
    assert 'aria-current="page">Spec delivery' in nav


@pytest.mark.spec("PIPE-PAGES-R019.3")
def test_repository_links_equal_single_source():
    nav = _nav(_page())
    links = re.findall(r'<li><a href="([^"]+)"( aria-current="true")?>', nav)
    assert [url for url, _ in links] == [anchor_for("repository", r, r) for r in ecosystem_components()]
    assert [bool(mark) for _, mark in links] == [True] + [False] * (len(links) - 1)


@pytest.mark.spec("PIPE-PAGES-R019.4")
def test_skip_link_targets_main():
    page = _page()
    assert 'class="skip" href="#main"' in page
    assert '<main id="main"' in page


@pytest.mark.spec("PIPE-PAGES-R019.5")
def test_page_keeps_existing_panels():
    page = _page()
    for title in ("Delivery structure", "Delivery states", "State definitions", "Specifications"):
        assert title in page
