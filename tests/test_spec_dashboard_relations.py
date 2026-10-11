"""Spec relationship model and view (PIPE-PAGES-R013)."""

import pytest

from scripts.spec_dashboard_relations import extends_edges, layer_specs, spec_edges
from scripts.spec_dashboard_relations_view import relation_table, relation_view


class Req:
    def __init__(self, id, spec, depends_on=()):
        self.id, self.spec, self.depends_on = id, spec, set(depends_on)


COUNTS = {"verified": 1, "landed": 0, "building": 0, "specified": 2}
CHAIN = [("B", "depends on", "A"), ("C", "extends", "B")]


@pytest.mark.spec("PIPE-PAGES-R013.1")
def test_spec_edges_lift_requirement_edges():
    reqs = [
        Req("A-1", "A"),
        Req("B-1", "B", ["A-1"]),
        Req("B-2", "B", ["A-1"]),
        Req("B-3", "B", ["B-1"]),
    ]
    assert spec_edges(reqs) == [("B", "depends on", "A")]


@pytest.mark.spec("PIPE-PAGES-R013.2")
def test_extends_edge_from_spec_md():
    texts = {"B": "# B\n\nExtends: A\n", "C": "# C\nno line\n"}
    assert extends_edges(texts) == [("B", "extends", "A")]


@pytest.mark.spec("PIPE-PAGES-R013.3")
def test_layers_by_dependency_depth():
    assert layer_specs(["A", "B", "C"], CHAIN) == {"A": 0, "B": 1, "C": 2}


@pytest.mark.spec("PIPE-PAGES-R013.3")
def test_cycle_layers_are_order_independent():
    edges = [
        ("X", "depends on", "X"),
        ("P", "depends on", "Q"),
        ("Q", "depends on", "R"),
        ("R", "depends on", "P"),
        ("P", "depends on", "ROOT"),
        ("OUT", "depends on", "Q"),
    ]
    nodes = ["X", "P", "Q", "R", "ROOT", "OUT"]
    first = layer_specs(nodes, edges)
    assert first == layer_specs(reversed(nodes), list(reversed(edges)))
    assert (
        first["ROOT"],
        first["X"],
        first["P"],
        first["Q"],
        first["R"],
        first["OUT"],
    ) == (0, 0, 1, 1, 1, 2)


@pytest.mark.spec("PIPE-PAGES-R013.4")
def test_relation_view_is_html_css():
    out = relation_view({n: COUNTS for n in "ABC"}, CHAIN)
    assert "<svg" not in out and "mermaid" not in out.lower()
    assert out.count('class="rel-box"') == 3


@pytest.mark.spec("PIPE-PAGES-R013.5")
def test_relation_view_has_legend_and_labels():
    out = relation_view({n: COUNTS for n in "ABC"}, CHAIN)
    assert (
        "rel-legend" in out and "<b>depends on</b>" in out and "<b>extends</b>" in out
    )


@pytest.mark.spec("PIPE-PAGES-R013.6")
def test_relation_table_matches_edges():
    out = relation_table({}, CHAIN)
    assert out.count("<tr><td>") == len(CHAIN)
    assert 'aria-describedby="relation-table"' in relation_view(
        {n: COUNTS for n in "ABC"}, CHAIN
    )


@pytest.mark.spec("PIPE-PAGES-R013.7")
def test_view_cap_falls_back_to_table():
    nodes = {f"S{i}": COUNTS for i in range(41)}
    edges = [(f"S{i}", "depends on", "S0") for i in range(1, 41)]
    out = relation_view(nodes, edges)
    assert "rel-box" not in out and "view limited to 40 specs; see table" in out
    assert out.count("<tr><td>") == 40


@pytest.mark.spec("PIPE-PAGES-R013")
def test_snapshot_edges_feed_relation_panel(tmp_path):
    from scripts.spec_dashboard_wiring import snapshot_edges

    (tmp_path / "specs" / "B").mkdir(parents=True)
    (tmp_path / "specs" / "B" / "spec.md").write_text("Extends: A\n")
    assert snapshot_edges(tmp_path) == [["B", "extends", "A"]]
