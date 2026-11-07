"""PIPE-GATES-R091: the consistency analysis checks the Phase 1 design answers."""

from __future__ import annotations

from pipelines_hooks.specs.analysis import check_design

ITEMS = {
    "Owner": "pipelines.",
    "Cohesion": "the check beside the analysis.",
    "Dependency direction": "toward analysis.",
    "Interface depth": "INTERFACE",
    "Special cases": "none, uniform.",
    "State": "none, no lifecycle.",
    "Environment": "none, no deployment variance.",
}


def _plan(depth: str, drop: str | None = None) -> str:
    items = {**ITEMS, "Interface depth": depth}
    lines = [f"- **{k}.** {v}" for k, v in items.items() if k != drop]
    return "# Plan\n\n## Phase 1: Design\n\n" + "\n".join(lines) + "\n\n## Phase 2: Tasks\n"


def test_all_answers_present_pass():
    # spec: PIPE-GATES-R091
    assert check_design(_plan("one function in `a/b.py`.")) == []


def test_no_design_section_is_not_checked():
    # spec: PIPE-GATES-R091
    assert check_design("# Plan\n\n## Summary\n") == []


def test_missing_item_is_a_finding_naming_it():
    # spec: PIPE-GATES-R091
    found = check_design(_plan("one function.", drop="Cohesion"))
    assert len(found) == 1 and "'Cohesion'" in found[0]


def test_one_call_site_is_a_finding():
    # spec: PIPE-GATES-R091
    found = check_design(_plan("a new interface `Port` used by `src/a.py`."))
    assert len(found) == 1 and "fewer than two call sites" in found[0]


def test_two_call_sites_pass():
    # spec: PIPE-GATES-R091
    assert check_design(_plan("a new interface `Port` used by `src/a.py` and `src/b.py`.")) == []


def test_none_with_reason_passes():
    # spec: PIPE-GATES-R091
    assert check_design(_plan("none: no new interface; concrete code in `src/a.py`.")) == []
