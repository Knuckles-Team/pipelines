"""PIPE-GATES-R086.9: algebraic checks over the states-by-events matrix of a table."""

from __future__ import annotations

from typing import Any

import pytest

from pipelines_hooks.code.state_machine_algebra import algebra_findings
from pipelines_hooks.code.state_machine_model import Machine
from pipelines_hooks.code.state_machine_rules import findings

#: QUEUED -start-> RUNNING -finish-> DONE; every missing cell has a refusal test.
EDGES = (("QUEUED", "start", "RUNNING"), ("RUNNING", "finish", "DONE"))
MISSING = {("QUEUED", "finish"), ("RUNNING", "start"), ("DONE", "start"), ("DONE", "finish")}


def _table(**fields: Any) -> Machine:
    values: dict[str, Any] = {
        "status_field": "status",
        "status_kind": "enum",
        "table": "TRANSITIONS",
        "edges": EDGES,
        "initial": "QUEUED",
        "terminals": ("DONE",),
        "function": "Job.apply",
        "refusal": "TransitionRefused",
        "bound": True,
        "refusal_tested": True,
        "refused_cells": set(MISSING),
    }
    return Machine("python", "pkg/job.py", 4, "Job", **{**values, **fields})


def _codes(machine: Machine) -> list[tuple[str, str]]:
    return [(f.code, f.detail) for f in algebra_findings(machine)]


@pytest.mark.spec("PIPE-GATES-R086.9")
def test_an_unreachable_state_is_reported() -> None:
    machine = _table(states=("QUEUED", "RUNNING", "DONE", "ORPHAN"), terminals=("DONE", "ORPHAN"))
    assert _codes(machine) == [
        ("SM-UNREACHABLE", "state ORPHAN"),
        ("SM-UNTESTED-REFUSAL", "from=ORPHAN event=start"),
        ("SM-UNTESTED-REFUSAL", "from=ORPHAN event=finish"),
    ]
    assert _codes(_table()) == []


@pytest.mark.spec("PIPE-GATES-R086.9")
def test_a_non_terminal_dead_end_is_reported() -> None:
    assert _codes(_table(terminals=())) == [("SM-DEAD-END", "state DONE")]


@pytest.mark.spec("PIPE-GATES-R086.9")
def test_a_terminal_state_with_an_outgoing_cell_is_reported() -> None:
    assert _codes(_table(terminals=("DONE", "RUNNING"))) == [("SM-TERMINAL-NOT-ABSORBING", "state RUNNING")]


@pytest.mark.spec("PIPE-GATES-R086.9")
def test_two_targets_for_one_state_and_event_are_reported() -> None:
    machine = _table(edges=(*EDGES, ("RUNNING", "finish", "QUEUED")))
    assert _codes(machine) == [("SM-NONDETERMINISTIC", "from=RUNNING event=finish to=DONE,QUEUED")]


@pytest.mark.spec("PIPE-GATES-R086.9")
def test_a_refusal_cell_without_a_test_is_reported() -> None:
    machine = _table(refused_cells=MISSING - {("DONE", "start")})
    found = [f for f in findings(machine) if f.rule == 6]
    assert [f.render() for f in found] == ["pkg/job.py:4 Job SM-UNTESTED-REFUSAL rule 6: from=DONE event=start"]
    assert _codes(_table(refused_cells=set(), product_refusal_test=True)) == []


@pytest.mark.spec("PIPE-GATES-R086.9")
def test_a_table_without_an_initial_state_is_reported() -> None:
    assert _codes(_table(initial=None)) == [("SM-NO-INITIAL", "table TRANSITIONS declares no INITIAL")]


@pytest.mark.spec("PIPE-GATES-R086.9")
def test_a_function_machine_has_no_matrix_checks() -> None:
    machine = _table(table=None, edges=(), initial=None, terminals=(), refused_cells=set())
    assert algebra_findings(machine) == []
    assert [f.code for f in findings(machine)] == []
