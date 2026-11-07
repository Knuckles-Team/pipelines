"""PIPE-GATES-R086: the state-machine rule set over hand-built ``Machine`` records."""

from __future__ import annotations

from typing import Any

import pytest

from pipelines_hooks.code.state_machine_model import Machine, Site
from pipelines_hooks.code.state_machine_rules import findings


def _machine(**fields: Any) -> Machine:
    base: dict[str, Any] = {"language": "python", "file": "pkg/job.py", "line": 3, "type_name": "Job"}
    return Machine(**{**base, **fields})


def _codes(machine: Machine) -> list[str]:
    return [finding.code for finding in findings(machine)]


def _declared(**fields: Any) -> Machine:
    values: dict[str, Any] = {
        "status_field": "status",
        "status_type": "JobStatus",
        "status_kind": "enum",
        "states": ("QUEUED", "DONE"),
        "table": "TRANSITIONS",
        "edges": (("QUEUED", "finish", "DONE"),),
        "initial": "QUEUED",
        "terminals": ("DONE",),
        "refused_cells": {("DONE", "finish")},
        "function": "Job.apply",
        "refusal": "TransitionRefused",
        "assigners": [Site("pkg/job.py", 20, "Job.apply")],
        "bound": True,
        "refusal_tested": True,
    }
    values.update(fields)
    return _machine(**values)


@pytest.mark.spec("PIPE-GATES-R086.1")
def test_a_status_assigned_from_two_functions_is_reported() -> None:
    undeclared = _machine(
        status_field="status",
        assigners=[Site("pkg/job.py", 10, "start"), Site("pkg/job.py", 14, "stop")],
    )
    assert _codes(undeclared) == ["SM-MULTI-ASSIGN", "SM-MULTI-ASSIGN"]
    stray = _declared(assigners=[Site("pkg/job.py", 20, "Job.apply"), Site("pkg/other.py", 7, "reset")])
    found = findings(stray)
    assert [(f.code, f.file, f.line) for f in found] == [("SM-MULTI-ASSIGN", "pkg/other.py", 7)]
    assert found[0].render() == "pkg/other.py:7 Job SM-MULTI-ASSIGN rule 1: assigned in reset"


@pytest.mark.spec("PIPE-GATES-R086.1")
def test_a_status_string_compare_without_an_enum_is_reported() -> None:
    machine = _declared(string_compares=[Site("pkg/view.py", 4, "render")])
    assert _codes(machine) == ["SM-STRING-STATUS"]
    assert findings(machine)[0].line == 4


@pytest.mark.spec("PIPE-GATES-R086.1")
def test_a_string_typed_status_field_is_reported() -> None:
    machine = _machine(status_field="status", status_type="str", status_kind="string")
    assert _codes(machine) == ["SM-STRING-STATUS"]
    assert findings(machine)[0].rule == 2


@pytest.mark.spec("PIPE-GATES-R086.1")
def test_lifecycle_booleans_beside_a_status_are_reported() -> None:
    machine = _declared(flags=("is_running", "cancel_requested"))
    assert _codes(machine) == ["SM-LIFECYCLE-FLAGS"]


@pytest.mark.spec("PIPE-GATES-R086.1")
def test_lifecycle_timestamps_without_a_status_are_reported() -> None:
    assert _codes(_machine(flags=("started_at", "finished_at"))) == ["SM-LIFECYCLE-FLAGS"]
    assert _codes(_machine(flags=("started_at",))) == []


@pytest.mark.spec("PIPE-GATES-R086.1")
def test_a_machine_without_refusal_tests_is_reported() -> None:
    machine = _declared(refusal_tested=False, untested_edges=[("QUEUED", "finish")])
    assert _codes(machine) == ["SM-UNTESTED-EDGE", "SM-NO-REFUSAL-TEST"]
    assert findings(machine)[0].detail == "from=QUEUED event=finish"
    assert _codes(_declared(refusal_tested=False, bound=False)) == []


@pytest.mark.spec("PIPE-GATES-R086.1")
def test_an_enum_status_without_a_declared_machine_is_reported() -> None:
    machine = _machine(status_field="status", status_type="JobStatus", status_kind="enum")
    assert _codes(machine) == ["SM-NO-DECLARATION"]
    assert findings(machine)[0].rule == 5


@pytest.mark.spec("PIPE-GATES-R086.1")
def test_a_declared_machine_with_full_tests_passes() -> None:
    assert findings(_declared()) == []
