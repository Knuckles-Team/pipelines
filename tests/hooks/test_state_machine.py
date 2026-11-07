"""PIPE-GATES-R086: the state-machine rule set over hand-built ``Machine`` records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipelines_hooks.code.state_machine_model import Machine, Site
from pipelines_hooks.code import state_machine
from pipelines_hooks.code.state_machine_rules import findings
from tests.hooks.state_machine_repo import fixture_repo


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


#: Fixture directory -> the codes its census run must report (both languages).
RULE_CASES = {
    "compliant": set(),
    "two_assigners": {"SM-MULTI-ASSIGN"},
    "string_compare": {"SM-STRING-STATUS"},
    "lifecycle_flags": {"SM-LIFECYCLE-FLAGS"},
    "no_refusal_tests": {"SM-NO-REFUSAL-TEST", "SM-UNTESTED-REFUSAL"},
}
ALGEBRA_CASES = {
    "compliant_algebra": set(),
    "unreachable_state": {"SM-UNREACHABLE"},
    "dead_end": {"SM-DEAD-END"},
    "terminal_exits": {"SM-TERMINAL-NOT-ABSORBING"},
    "nondeterministic": {"SM-NONDETERMINISTIC"},
    "untested_refusal": {"SM-UNTESTED-REFUSAL"},
}


def _census_codes(tmp_path: Path, case: str) -> set[str]:
    root = fixture_repo(tmp_path / case.replace("/", "-"), case)
    return {finding.code for finding in state_machine.run(root, census=True).findings}


def _check_cases(tmp_path: Path, cases: dict[str, set[str]]) -> None:
    for language in ("py", "rs"):
        for case, expected in cases.items():
            assert _census_codes(tmp_path, f"{language}/{case}") == expected, f"{language}/{case}"


@pytest.mark.spec("PIPE-GATES-R086")
@pytest.mark.spec("PIPE-GATES-R086.8")
def test_the_census_reports_every_fixture_violation_and_passes_the_compliant_tree(tmp_path: Path) -> None:
    _check_cases(tmp_path, RULE_CASES)


@pytest.mark.spec("PIPE-GATES-R086.10")
def test_the_census_reports_every_algebraic_violation_and_passes_the_compliant_tree(tmp_path: Path) -> None:
    _check_cases(tmp_path, ALGEBRA_CASES)
