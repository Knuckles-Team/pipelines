"""Canopy open research questions (PIPE-PAGES-R058)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import build as explorer  # noqa: E402
from scripts.architecture_explorer import sdd  # noqa: E402

RESEARCH = (
    "# Research\n\n## Decisions\n\n- [ ] not a question FAM-R009\n\n## Open questions\n\n"
    "- [ ] Which index serves FAM-R001?\n- [x] Settled one\n- [ ] A family-wide question\n\n"
    "## Unresolved\n\n- [ ] Is FAM-R002 retired?\n"
)
SPEC = "# FAM - Fam\n\nThe cutoff is [NEEDS CLARIFICATION: how long?] for FAM-R002.\n"


@pytest.mark.spec("PIPE-PAGES-R058.1")
def test_open_questions_find_markers_and_unchecked_research_items() -> None:
    found = sdd.open_questions({"spec.md": SPEC, "research.md": RESEARCH})
    by_kind = {(q["kind"], q["doc"], q["line"], q["row"]) for q in found}
    assert ("marker", "spec.md", 3, "FAM-R002") in by_kind
    assert ("open", "research.md", 9, "FAM-R001") in by_kind
    assert ("open", "research.md", 11, "") in by_kind
    assert ("open", "research.md", 15, "FAM-R002") in by_kind
    assert len(found) == 4  # the checked item and the item under Decisions are no questions
    assert set(found[0]) == {"kind", "text", "doc", "line", "row"}


@pytest.mark.spec("PIPE-PAGES-R058.2")
def test_counts_follow_the_own_rows_rule_and_zero_shows_no_badge() -> None:
    rows = [{"id": "FAM-R001", "status": "SPECIFIED"}, {"id": "FAM-R002", "status": "SPECIFIED"}]
    card = sdd.family_card({"spec.md": SPEC, "research.md": RESEARCH}, set(), "fam", [], rows)
    assert card["q"] == 4
    quiet = sdd.family_card({"spec.md": "# FAM - Fam\n"}, set(), "fam", [], rows)
    assert "q" not in quiet and "u" not in quiet
    snap = type(
        "S",
        (),
        {
            "repo": "r",
            "rows": [dict(r, family="fam") for r in rows],
            "files": set(),
            "docs": {"fam": {"spec.md": SPEC, "research.md": RESEARCH}},
        },
    )
    cards = {"r": {"fam": card}}
    _, counts = explorer.row_facts([snap], cards, set())
    assert counts == {"FAM-R001": 1, "FAM-R002": 2}
    entry = explorer.spec_entry(
        dict(rows[1], repo="r", family="fam", title="t"),
        {"scores": {}, "frontier_set": set(), "unserved_set": set(), "row_questions": counts},
    )
    assert entry["q"] == 2
    zero = explorer.spec_entry(
        dict(rows[0], repo="r", family="fam", title="t"),
        {"scores": {}, "frontier_set": set(), "unserved_set": set(), "row_questions": {}},
    )
    assert "q" not in zero


@pytest.mark.spec("PIPE-PAGES-R058.4")
def test_unreadable_research_marks_the_family_without_failing_the_build() -> None:
    files = {"specs/fam/research.md", "specs/fam/spec.md"}
    found = sdd.open_questions({"spec.md": "# FAM\n"}, files, "fam")
    assert [q["kind"] for q in found] == ["unreadable"]
    card = sdd.family_card({"spec.md": "# FAM\n"}, files, "fam", [], [{"id": "FAM-R001", "status": "SPECIFIED"}])
    assert card["u"] == "research unreadable" and "q" not in card
    # An unchecked item outside an open-questions heading is not a question.
    assert sdd.open_questions({"research.md": "# R\n\n## Notes\n\n- [ ] later\n"}) == []
