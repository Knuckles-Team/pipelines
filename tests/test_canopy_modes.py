"""Canopy diagram modes: the SDD phase of a spec family (PIPE-PAGES-R054)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import sdd  # noqa: E402
from scripts.architecture_explorer.sdd import SddPhase  # noqa: E402

SPEC = "# FAM - Fam\n\n## Purpose\n\nWhy.\n"
TASKS_OPEN = "# Tasks\n\n- [ ] T001 FAM-R001 do it\n- [ ] T002 FAM-R002 do it\n"
TASKS_STARTED = "# Tasks\n\n- [x] T001 FAM-R001 do it\n- [ ] T002 FAM-R002 do it\n"


def _rows(*states: str) -> list[dict]:
    return [{"id": f"FAM-R00{i}", "status": s} for i, s in enumerate(states, 1)]


@pytest.mark.spec("PIPE-PAGES-R054.1")
def test_sdd_phase_enum_orders_six_phases() -> None:
    assert [p.label for p in SddPhase] == [
        "specified",
        "research-done",
        "plan-accepted",
        "tasks-ready",
        "implementing",
        "verified",
    ]
    assert list(SddPhase) == sorted(SddPhase) and set(sdd.PHASE_PREDICATES) == set(SddPhase)
    card = sdd.family_card({"spec.md": SPEC}, set(), "fam", [], _rows("SPECIFIED"))
    assert card["s"] == int(SddPhase.RESEARCH_DONE)
    assert sdd.family_card({}, set(), "fam", [], _rows("SPECIFIED"))["s"] == 0


@pytest.mark.spec("PIPE-PAGES-R054.2")
def test_each_phase_predicate_holds_only_on_its_artifacts() -> None:
    clean = lambda text: []  # noqa: E731
    broken = lambda text: ["1: missing heading"]  # noqa: E731
    rows = _rows("SPECIFIED", "SPECIFIED")

    def phase(docs, rows=rows, check=clean):
        return sdd.sdd_phase(docs, rows, check(docs.get("plan.md", "")) if docs.get("plan.md") else None)

    assert sdd.sdd_phase({}, rows) is None
    assert phase({"spec.md": SPEC}) == SddPhase.RESEARCH_DONE
    # A clarification marker anywhere holds the family at specified.
    assert phase({"spec.md": SPEC + "\n[NEEDS CLARIFICATION: who?]\n"}) == SddPhase.SPECIFIED
    # An unchecked item under an open-questions heading of research.md holds it there too; elsewhere it is no question.
    open_research = "# Research\n\n## Open questions\n\n- [ ] Which index?\n"
    assert phase({"spec.md": SPEC, "research.md": open_research}) == SddPhase.SPECIFIED
    assert phase({"spec.md": SPEC, "research.md": "# Research\n\n## Notes\n\n- [ ] later\n"}) == SddPhase.RESEARCH_DONE
    docs = {"spec.md": SPEC, "plan.md": "# plan\n"}
    assert phase(docs, check=broken) == SddPhase.RESEARCH_DONE
    assert phase(docs, check=clean) == SddPhase.PLAN_ACCEPTED
    docs["tasks.md"] = "# Tasks\n\n- [ ] T001 FAM-R001 only one\n"
    assert phase(docs) == SddPhase.PLAN_ACCEPTED  # FAM-R002 has no task line
    docs["tasks.md"] = TASKS_OPEN
    assert phase(docs) == SddPhase.TASKS_READY
    docs["tasks.md"] = TASKS_STARTED
    assert phase(docs) == SddPhase.IMPLEMENTING
    docs["tasks.md"] = TASKS_OPEN
    assert phase(docs, rows=_rows("LANDED", "SPECIFIED")) == SddPhase.IMPLEMENTING
    assert phase(docs, rows=_rows("VERIFIED", "VERIFIED")) == SddPhase.VERIFIED
    assert phase(docs, rows=_rows("VERIFIED", "RETIRED")) == SddPhase.VERIFIED  # retired rows do not count
    # A retired or rollup row needs no task line.
    docs["tasks.md"] = "# Tasks\n\n- [ ] T001 FAM-R001 only one\n"
    mixed = [{"id": "FAM-R001", "status": "SPECIFIED"}, {"id": "FAM-R002", "status": "SPECIFIED", "rollup": True}]
    assert phase(docs, rows=mixed) == SddPhase.TASKS_READY


@pytest.mark.spec("PIPE-PAGES-R054.2")
def test_plan_conformance_wrapper_reports_findings_for_text() -> None:
    from pipelines_hooks.specs.plan_conformance import check_plan_text

    template = "# <SPEC-ID> — Implementation plan\n\n## Summary\n\nx\n\n## Build contract\n\ny\n"
    good = "# FAM-X — Implementation plan\n\n## Summary\n\nDone.\n\n## Build contract\n\nDone.\n"
    assert check_plan_text(good, template, {"FAM-X-R001"}) == []
    found = check_plan_text("# FAM-X — Implementation plan\n\n## Summary\n\nDone.\n", template, set())
    assert any("Build contract" in f for f in found)
