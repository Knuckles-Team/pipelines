"""Drill-down URL forms and parity check."""

import pytest

from scripts.spec_dashboard_drilldown import (
    REPOS,
    anchor_for,
    check_drilldown_links,
    drilldown_exit,
    ecosystem_components,
)


def page(components):
    return "".join(f'<a href="{anchor_for("repository", "", c)}">{c}</a>' for c in components)


@pytest.mark.spec("PIPE-PAGES-R014.1")
def test_components_equal_core_list():
    assert ecosystem_components() == list(REPOS)


@pytest.mark.spec("PIPE-PAGES-R014.2")
def test_anchor_forms():
    base = "https://knuckles-team.github.io/r/spec-delivery/"
    assert anchor_for("repository", "x", "r") == base
    assert anchor_for("spec", "S1", "r") == base + "#spec-S1"
    assert anchor_for("requirement", "S1-R1", "r") == base + "#req-S1-R1"
    assert anchor_for("spec", "S1") == "#spec-S1"


@pytest.mark.spec("PIPE-PAGES-R014.6")
def test_unresolved_component_link_fails():
    comps = ecosystem_components()
    ok = page(comps) + '<a href="#spec-A"></a><section id="spec-A"></section>'
    assert drilldown_exit(ok) == 0
    assert drilldown_exit(page(comps[1:])) == 1
    assert check_drilldown_links(ok + '<a href="#req-Z"></a>') == ["unresolved anchor: #req-Z"]


@pytest.mark.spec("PIPE-PAGES-R014.3")
def test_spec_section_has_anchor():
    from scripts.spec_dashboard_panels import spec_row

    spec = {"id": "S-1", "title": "t", "delivery_state": "VERIFIED", "done": True}
    assert 'id="spec-S-1"' in spec_row(spec, [], lambda item, label: label)


@pytest.mark.spec("PIPE-PAGES-R014.4")
def test_relation_box_links_to_spec_section():
    from scripts.spec_dashboard_relations_view import box

    html = box("S-1", {}, [])
    assert 'href="#spec-S-1"' in html
    assert check_drilldown_links('<tr id="spec-S-1"></tr>' + html, []) == []
