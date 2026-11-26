"""The delivered qualification of a spec row (PIPE-RELEASE-R022)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts import release_delivered as d  # noqa: E402

BEHAVIOUR = "**Gate.** Caller chain: a hook -> main. | Test: `tests/test_x.py::test_y` (L3, served). |"
UNPROVEN = "**Gate.** Caller chain: a hook -> main. | Test: `tests/test_x.py::test_y`. |"
PASSED = {"passed": True}


# spec: PIPE-RELEASE-R022
def test_each_failing_condition_blocks_delivered() -> None:
    reach = {"R": True}
    assert d.delivered("R", "VERIFIED", reach, PASSED, BEHAVIOUR) is None
    assert d.delivered("R", "LANDED", reach, PASSED, BEHAVIOUR) == d.NOT_VERIFIED
    assert d.delivered("R", "VERIFIED", reach, PASSED, UNPROVEN) == d.PROOF_LEVEL
    assert d.delivered("R", "VERIFIED", {"R": False}, PASSED, BEHAVIOUR) == d.NOT_REACHABLE
    assert d.delivered("R", "VERIFIED", reach, {"passed": False}, BEHAVIOUR) == d.SCENARIO_NOT_PASSED
    assert d.delivered("R", "VERIFIED", reach, None, BEHAVIOUR) == d.SCENARIO_NOT_PASSED
    # The first failing condition wins, in the order of the standard.
    assert d.delivered("R", "SPECIFIED", {}, None, UNPROVEN) == d.NOT_VERIFIED
    rows = {"R": {"status": "VERIFIED", "text": BEHAVIOUR}, "S": {"status": "LANDED", "text": ""}}
    assert d.open_rows(["R", "S", "T"], rows, reach, PASSED) == {"S": d.NOT_VERIFIED, "T": "UNKNOWN_ROW"}
