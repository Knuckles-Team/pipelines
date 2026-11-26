"""The delivered qualification of a spec row (PIPE-RELEASE-R022).

Delivered is computed, never stored. A row is delivered when all four hold:

1. it is VERIFIED;
2. its bound test runs at the proof level its acceptance names (a behaviour row names L3 or L4, a served test);
3. the code it adds is reachable from a production caller under its repository's reachability gate;
4. the latest scenario run of its release's phase passed.

``delivered`` returns the first failing condition, or ``None`` when the row is delivered.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

NOT_VERIFIED = "NOT_VERIFIED"
PROOF_LEVEL = "PROOF_LEVEL"
NOT_REACHABLE = "NOT_REACHABLE"
SCENARIO_NOT_PASSED = "SCENARIO_NOT_PASSED"
VERIFIED = "VERIFIED"
_LEVEL = re.compile(r"\bL([0-4])\b")
_BEHAVIOUR = re.compile(r"Caller chain:")


def proof_level(text: str) -> int | None:
    """The highest proof level (L0 to L4) the row's verification text names, or None."""
    verification = text.rsplit("|", 2)[-2] if text.count("|") >= 2 else text
    levels = [int(n) for n in _LEVEL.findall(verification)]
    return max(levels) if levels else None


def delivered(
    row_id: str, status: str, reach: Mapping[str, bool], scenario_run: Mapping | None, text: str = ""
) -> str | None:
    """The first failing condition of the row, in the order above; ``None`` when it is delivered."""
    if status != VERIFIED:
        return NOT_VERIFIED
    if _BEHAVIOUR.search(text) and (proof_level(text) or 0) < 3:
        return PROOF_LEVEL
    if not reach.get(row_id, False):
        return NOT_REACHABLE
    if not scenario_run or not scenario_run.get("passed"):
        return SCENARIO_NOT_PASSED
    return None


def open_rows(
    ids: list[str], rows: Mapping[str, dict], reach: Mapping[str, bool], scenario_run: Mapping | None
) -> dict[str, str]:
    """Row ID -> first failing condition, for every row that is not delivered."""
    found = {}
    for rid in sorted(ids):
        row = rows.get(rid)
        why = (
            "UNKNOWN_ROW"
            if row is None
            else delivered(rid, row.get("status", ""), reach, scenario_run, row.get("text", ""))
        )
        if why:
            found[rid] = why
    return found
