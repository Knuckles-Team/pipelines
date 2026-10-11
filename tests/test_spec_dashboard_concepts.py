import pytest

from scripts.skill_graph.render_pages import render_concepts_md
from scripts.spec_dashboard_concepts import (
    concept_links,
    concepts_for_row,
    explicit_concepts,
    row_concepts,
    unmapped_count,
)


@pytest.mark.spec("PIPE-PAGES-R012.1")
def test_concepts_for_row_reads_markers(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("# CONCEPT:AU-1.2\n# CONCEPT:KG-3\n")
    assert concepts_for_row(["pkg"], [tmp_path]) == ["AU-1.2", "KG-3"]


@pytest.mark.spec("PIPE-PAGES-R012.2")
def test_explicit_concepts_override(tmp_path):
    (tmp_path / "a.py").write_text("# CONCEPT:DERIVED\n")
    text = "Concepts: B-1, A-2\n"
    assert explicit_concepts(text) == ["A-2", "B-1"]
    assert row_concepts(text, ["a.py"], [tmp_path]) == ["A-2", "B-1"]


@pytest.mark.spec("PIPE-PAGES-R012.3")
def test_concepts_md_has_anchor_per_concept(monkeypatch):
    import scripts.skill_graph.render_pages as rp

    nodes = [{"label": "Graph Core"}, {"label": "Ops"}]
    monkeypatch.setattr(rp, "group_concepts_by_repo", lambda c: {"x": nodes})
    monkeypatch.setattr(rp, "repo_label", lambda r: r)
    out = render_concepts_md({"@graph": []})
    assert 'id="concept-graph-core"' in out and 'id="concept-ops"' in out


@pytest.mark.spec("PIPE-PAGES-R012.4")
def test_concept_links_and_marker():
    out = concept_links(["A-1", "B-2"], "https://x/")
    assert out.count("<a ") == 2 and "#concept-a-1" in out
    empty = concept_links([], "https://x/")
    assert "no concept mapped" in empty and 'class="no-concept"' in empty
    assert unmapped_count([["A"], [], []]) == 2
