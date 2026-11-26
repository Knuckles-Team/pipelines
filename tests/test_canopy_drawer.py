"""Canopy row drawer: the detail record of one row (PIPE-PAGES-R053)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import delivery as delivery_mod  # noqa: E402
from scripts.architecture_explorer import details  # noqa: E402

PLAN = "# FAM - Plan\n\n## Summary\n\nThe solver handles FAM-R001 first.\n\nUnrelated paragraph.\n\nFAM-R001.1 is a child.\n"
TASKS = "# Tasks\n\n- [x] T001 FAM-R001 write the solver\n- [ ] T002 FAM-R001 prove it\n- [ ] T003 FAM-R002 other\n"
CHECK = "# Checklist\n\n- [x] FAM-R001 has a test\n- [ ] FAM-R002 has a test\n"
DOCS = {"plan.md": PLAN, "tasks.md": TASKS, "checklists/req.md": CHECK, "spec.md": "# FAM\n\nNothing here.\n"}


def _drawer(row_id: str, docs=DOCS, delivery=None) -> dict:
    return details.row_drawer(docs, row_id, details.Ctx("pipelines", "fam"), delivery, set(), "fam")


@pytest.mark.spec("PIPE-PAGES-R053.1")
def test_row_drawer_model_has_excerpts_tasks_checklist_and_unblocks() -> None:
    rows = [
        {"id": "FAM-R001", "repo": "pipelines", "status": "SPECIFIED", "family": "fam", "depends_on": []},
        {"id": "FAM-R002", "repo": "pipelines", "status": "SPECIFIED", "family": "fam", "depends_on": ["FAM-R001"]},
        {"id": "FAM-R003", "repo": "pipelines", "status": "VERIFIED", "family": "fam", "depends_on": ["FAM-R001"]},
    ]
    agg = delivery_mod.aggregate(rows)
    assert agg["dependents"] == {"FAM-R001": ["FAM-R002"]}  # only open rows are unblocked
    drawer = _drawer("FAM-R001", delivery=agg)
    assert set(drawer) == {
        "excerpts",
        "none",
        "tasks",
        "progress",
        "checklist",
        "unblocks",
        "cqs",
        "priority",
        "questions",
    }
    assert drawer["unblocks"] == ["FAM-R002"] and drawer["priority"] == agg["scores"]["FAM-R001"]["priority"]
    assert drawer["tasks"] == [
        {"done": True, "text": "T001 FAM-R001 write the solver"},
        {"done": False, "text": "T002 FAM-R001 prove it"},
    ]
    assert drawer["progress"] == [1, 2]
    assert drawer["checklist"] == [{"done": True, "text": "FAM-R001 has a test"}]
    assert all(len(html) <= details.EXCERPT_MAX for html in drawer["excerpts"].values())


@pytest.mark.spec("PIPE-PAGES-R053.2")
def test_excerpts_hold_only_paragraphs_that_name_the_row() -> None:
    drawer = _drawer("FAM-R001")
    plan = drawer["excerpts"]["plan"]
    assert "solver handles FAM-R001" in plan and "Unrelated" not in plan and "child" not in plan  # not the longer ID
    assert drawer["excerpts"]["spec"] == "" and "spec" in drawer["none"] and "plan" not in drawer["none"]
    assert drawer["none"] == ["spec", "test-spec"]
    # A row with no match anywhere has an empty excerpt and the none marker for every kind.
    empty = _drawer("FAM-R404")
    assert set(empty["none"]) == {"spec", "plan", "test-spec", "checklists"} and not any(empty["excerpts"].values())
    assert empty["tasks"] == [] and empty["progress"] == [0, 0]
    # A very long paragraph is cut so the rendered HTML stays within the limit; raw HTML is escaped.
    big = {"plan.md": "FAM-R001 <script>x</script> " + "word " * 600}
    out = _drawer("FAM-R001", big)["excerpts"]["plan"]
    assert 0 < len(out) <= details.EXCERPT_MAX and "<script>" not in out
