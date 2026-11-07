"""PIPE-GATES-R086.4: each edge and the refusal of a declared machine need a test."""

from __future__ import annotations

import textwrap

import pytest

from pipelines_hooks.code.state_machine_model import Machine
from pipelines_hooks.code.state_machine_rules import findings
from pipelines_hooks.code.state_machine_tests import bind_tests


def _machine() -> Machine:
    return Machine(
        "python",
        "pkg/job.py",
        5,
        "Job",
        status_field="status",
        status_type="JobStatus",
        status_kind="enum",
        table="TRANSITIONS",
        edges=(("QUEUED", "start", "RUNNING"), ("InProgress", "finish", "DONE")),
        function="Job.apply",
        refusal="TransitionRefused",
    )


def _bind(source: str, path: str = "tests/test_job.py") -> Machine:
    machine = _machine()
    bind_tests(machine, [(path, textwrap.dedent(source))])
    return machine


REFUSAL = """
def test_an_illegal_event_is_refused():
    with pytest.raises(TransitionRefused):
        Job().apply("bogus")
"""


@pytest.mark.spec("PIPE-GATES-R086.4")
def test_each_edge_needs_a_test_naming_its_from_state_and_event() -> None:
    machine = _bind(
        REFUSAL
        + """
def test_queued_start_runs():
    pass

def test_in_progress_finish_is_done():
    pass
"""
    )
    assert machine.bound and machine.untested_edges == [] and machine.refusal_tested
    assert [f for f in findings(machine) if f.rule == 4] == []
    partial = _bind(REFUSAL + "def test_queued_start_runs():\n    pass\n")
    assert partial.untested_edges == [("InProgress", "finish")]


@pytest.mark.spec("PIPE-GATES-R086.4")
def test_a_parametrize_id_binds_an_edge() -> None:
    machine = _bind(
        REFUSAL
        + """
@pytest.mark.parametrize(
    "case",
    [pytest.param(1, id="queued-start"), pytest.param(2, id="in_progress-finish")],
)
def test_edges(case):
    pass
"""
    )
    assert machine.untested_edges == []
    rust = _machine()
    bind_tests(rust, [("tests/job.rs", "#[test]\nfn queued_start_runs() {}\n#[test]\nfn in_progress_finish() {}\n")])
    assert rust.untested_edges == []


@pytest.mark.spec("PIPE-GATES-R086.4")
def test_the_refusal_test_must_name_the_refusal_type() -> None:
    nameless = _bind("def test_an_illegal_event_is_refused():\n    assert Job().apply('x') is None\n")
    assert not nameless.refusal_tested
    assert "SM-NO-REFUSAL-TEST" in [f.code for f in findings(nameless)]
    misnamed = _bind("def test_bogus_event():\n    raise TransitionRefused()\n")
    assert not misnamed.refusal_tested
    assert _bind(REFUSAL).refusal_tested


@pytest.mark.spec("PIPE-GATES-R086.4")
def test_a_missing_edge_test_names_the_edge() -> None:
    machine = _bind(REFUSAL)
    rendered = [f.render() for f in findings(machine) if f.code == "SM-UNTESTED-EDGE"]
    assert rendered == [
        "pkg/job.py:5 Job SM-UNTESTED-EDGE rule 4: from=QUEUED event=start",
        "pkg/job.py:5 Job SM-UNTESTED-EDGE rule 4: from=InProgress event=finish",
    ]
