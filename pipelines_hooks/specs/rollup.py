"""Parent/child rollup: a parent's state is the minimum of its live children's states.

A parent that rolls up to LANDED or VERIFIED also carries its live children's
evidence (landing commits, and bound tests when VERIFIED), so a delivered
rollup never publishes a delivered state with empty evidence.
"""

from __future__ import annotations

from pipelines_hooks.specs.ids import ORDER
from pipelines_hooks.specs.records import MAX_EVIDENCE_SHOWN

#: Which evidence field a rolled-up state must carry.
_EVIDENCE = {"LANDED": ("landed_in",), "VERIFIED": ("landed_in", "verified_by")}


def _direct_children(parent: str, ids: list[str]) -> list[str]:
    return [child for child in ids if child.rsplit(".", 1)[0] == parent and "." in child[len(parent) :]]


def apply_rollup(ids: list[str], state: dict[str, str], records: dict[str, dict[str, object]]) -> None:
    """Mutate ``state``/``records`` in place, deepest requirement first."""
    for parent in sorted(ids, key=lambda rid: -rid.count(".")):
        if state[parent] == "RETIRED":
            continue
        children = _direct_children(parent, ids)
        if not children:
            continue
        live = [state[child] for child in children if state[child] != "RETIRED"]
        rolled = min(live, key=lambda value: ORDER.get(value, -1)) if live else "RETIRED"
        state[parent] = rolled
        records[parent]["delivery_state"] = rolled
        records[parent]["rollup_of"] = children
        live_children = [child for child in children if state[child] != "RETIRED"]
        for field in _EVIDENCE.get(rolled, ()):
            records[parent][field] = _merged_evidence(records, parent, live_children, field)


def _merged_evidence(records: dict[str, dict[str, object]], parent: str, children: list[str], field: str) -> list[str]:
    """The parent's own evidence and each live child's, de-duplicated and sorted.

    Sorted, not first-seen: the next run carries this list forward as the parent's own
    landings, so any order that depends on the input would rewrite the file every run.
    """
    merged: set[str] = set()
    for rid in [parent, *children]:
        values = records[rid].get(field, [])
        merged.update(values if isinstance(values, list) else [])
    return sorted(merged)[:MAX_EVIDENCE_SHOWN]


def overall_state(state: dict[str, str]) -> str:
    """The spec-level state: the minimum of every non-retired requirement."""
    live = [value for value in state.values() if value != "RETIRED"]
    return min(live, key=lambda value: ORDER.get(value, -1)) if live else "RETIRED"
