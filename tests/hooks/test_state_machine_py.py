"""PIPE-GATES-R086.2: the Python reader builds ``Machine`` records with ``ast``."""

from __future__ import annotations

import ast
import textwrap

import pytest

from pipelines_hooks.code.state_machine_model import Machine
from pipelines_hooks.code.state_machine_py import loose_sites, read_python

STATUS_ENUM = """
from enum import StrEnum

class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
"""


def _read(source: str, path: str = "pkg/job.py") -> list[Machine]:
    return read_python(path, ast.parse(textwrap.dedent(source)))


def _job(source: str) -> Machine:
    (machine,) = [m for m in _read(STATUS_ENUM + textwrap.dedent(source)) if m.type_name == "Job"]
    return machine


@pytest.mark.spec("PIPE-GATES-R086.2")
def test_python_reader_recognises_a_transitions_constant() -> None:
    machine = _job(
        """
        TRANSITIONS = {
            (JobStatus.QUEUED, "start"): JobStatus.RUNNING,
            (JobStatus.RUNNING, "finish"): JobStatus.DONE,
        }

        class Job:
            status: JobStatus
        """
    )
    assert machine.table == "TRANSITIONS"
    assert machine.edges == (("QUEUED", "start", "RUNNING"), ("RUNNING", "finish", "DONE"))
    assert machine.status_kind == "enum"
    assert machine.states == ("QUEUED", "RUNNING", "DONE")
    assert machine.declared


@pytest.mark.spec("PIPE-GATES-R086.2")
def test_python_reader_recognises_an_apply_that_raises_a_refusal() -> None:
    machine = _job(
        """
        class TransitionRefused(Exception):
            pass

        class Job:
            status: JobStatus

            def apply(self, event: str) -> None:
                if event != "start":
                    raise TransitionRefused(event)
                self.status = JobStatus.RUNNING
        """
    )
    assert (machine.function, machine.refusal) == ("Job.apply", "TransitionRefused")
    assert [site.function for site in machine.assigners] == ["Job.apply"]
    undeclared = _job("class Job:\n    status: JobStatus\n\n    def apply(self) -> None:\n        raise ValueError()\n")
    assert undeclared.function is None and not undeclared.declared


@pytest.mark.spec("PIPE-GATES-R086.2")
def test_python_self_receiver_resolves_to_the_enclosing_class() -> None:
    machines = _read(
        """
        class Job:
            status: str

            def start(self) -> None:
                self.status = "running"

        class Task:
            status: str

            def start(self) -> None:
                self.status = "running"

            def done(self) -> bool:
                return self.status == "done"
        """
    )
    by_name = {m.type_name: m for m in machines}
    assert [s.function for s in by_name["Job"].assigners] == ["Job.start"]
    assert [s.function for s in by_name["Task"].assigners] == ["Task.start"]
    assert [s.function for s in by_name["Task"].string_compares] == ["Task.done"]
    assert by_name["Job"].status_kind == "string"


@pytest.mark.spec("PIPE-GATES-R086.2")
def test_python_setattr_and_replace_count_as_assignments() -> None:
    source = """
    import dataclasses

    class Job:
        status: str
        started_at: str | None
        finished_at: Optional[str]
        is_running: bool

    def a(job):
        setattr(job, "status", "x")

    def b(job):
        return dataclasses.replace(job, status="y")

    def c(job):
        return job.model_copy(update={"status": "z"})

    def d(job):
        job.status = "w"
    """
    (machine,) = _read(source)
    assert [s.function for s in machine.assigners] == ["a", "b", "c", "d"]
    assert machine.flags == ("started_at", "finished_at", "is_running")
    assert [use.site.function for use in loose_sites("pkg/job.py", ast.parse(textwrap.dedent(source)))] == [
        "a",
        "b",
        "c",
        "d",
    ]


@pytest.mark.spec("PIPE-GATES-R086.2")
def test_python_reader_skips_test_files() -> None:
    source = "class Job:\n    status: str\n"
    assert _read(source, "tests/test_job.py") == []
    assert _read(source, "pkg/test_job.py") == []
    assert _read(source, "pkg/conftest.py") == []
    assert len(_read(source, "pkg/job.py")) == 1
