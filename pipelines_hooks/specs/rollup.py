"""Parent/child rollup: a parent's state is the minimum of its live children's states."""

from __future__ import annotations

from pipelines_hooks.specs.ids import ORDER


def _direct_children(parent: str, ids: list[str]) -> list[str]:
    return [child for child in ids if child.rsplit(".", 1)[0] == parent and "." in child[len(parent):]]


def apply_rollup(ids: list[str], state: dict[str, str], records: dict[str, dict[str, object]]) -> None:
    """Mutate ``state``/``records`` in place, deepest requirement first."""
    for parent in sorted(ids, key=lambda rid: -rid.count(".")):
        if state[parent] == "RETIRED":
            continue
        children = _direct_children(parent, ids)
        if not children:
            continue
        live = [state[child] for child in children if state[child] != "RETIRED"]
        rolled = min(live, key=ORDER.get) if live else "RETIRED"
        state[parent] = rolled
        records[parent]["delivery_state"] = rolled
        records[parent]["rollup_of"] = children


def overall_state(state: dict[str, str]) -> str:
    """The spec-level state: the minimum of every non-retired requirement."""
    live = [value for value in state.values() if value != "RETIRED"]
    return min(live, key=ORDER.get) if live else "RETIRED"
