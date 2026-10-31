from pipelines_hooks.specs.rollup import apply_rollup


def _records(state):
    return {rid: {"id": rid, "delivery_state": value} for rid, value in state.items()}


def test_parent_with_only_retired_children_keeps_its_own_state():
    ids = ["X-R1", "X-R1.1"]
    state = {"X-R1": "VERIFIED", "X-R1.1": "RETIRED"}
    records = _records(state)
    apply_rollup(ids, state, records)
    assert state["X-R1"] == "VERIFIED"
    assert records["X-R1"]["delivery_state"] == "VERIFIED"


def test_parent_rolls_up_to_its_least_delivered_live_child():
    ids = ["X-R1", "X-R1.1", "X-R1.2", "X-R1.3"]
    state = {"X-R1": "SPECIFIED", "X-R1.1": "VERIFIED", "X-R1.2": "LANDED", "X-R1.3": "RETIRED"}
    records = _records(state)
    apply_rollup(ids, state, records)
    assert state["X-R1"] == "LANDED"
