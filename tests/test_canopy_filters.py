"""Canopy Next-step chips (PIPE-PAGES-R055)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer.sdd import SddPhase, next_step  # noqa: E402

CASES = [
    # (state, phase, in Next up, chip)
    ("SPECIFIED", SddPhase.SPECIFIED, False, "research"),
    ("SPECIFIED", SddPhase.RESEARCH_DONE, False, "plan"),
    ("SPECIFIED", SddPhase.PLAN_ACCEPTED, False, ""),
    ("SPECIFIED", SddPhase.TASKS_READY, True, "ready"),
    ("SPECIFIED", SddPhase.IMPLEMENTING, True, "ready"),
    ("SPECIFIED", SddPhase.TASKS_READY, False, ""),
    ("LANDED", SddPhase.IMPLEMENTING, False, "verify"),
    ("VERIFIED", SddPhase.VERIFIED, False, ""),
    ("RETIRED", 0, False, ""),
]


@pytest.mark.spec("PIPE-PAGES-R055.1")
def test_next_step_maps_phase_and_state_to_one_chip() -> None:
    for state, phase, frontier, chip in CASES:
        assert next_step({"status": state}, int(phase), frontier) == chip, (state, phase, frontier)


@pytest.mark.spec("PIPE-PAGES-R055.2")
def test_chip_rules_follow_the_documented_order() -> None:
    # verify beats ready: a LANDED row in Next up at an implementing family is verified next.
    assert next_step({"status": "LANDED"}, int(SddPhase.IMPLEMENTING), True) == "verify"
    # ready beats plan and research: it only applies at tasks-ready or implementing, so the lower phases fall through.
    assert next_step({"status": "SPECIFIED"}, int(SddPhase.RESEARCH_DONE), True) == "plan"
    assert next_step({"status": "SPECIFIED"}, int(SddPhase.SPECIFIED), True) == "research"
    # Every (state, phase, frontier) combination yields at most one chip value.
    chips = {
        next_step({"status": s}, int(p), f)
        for s in ("SPECIFIED", "LANDED", "VERIFIED")
        for p in SddPhase
        for f in (True, False)
    }
    assert chips <= {"verify", "ready", "plan", "research", ""}
