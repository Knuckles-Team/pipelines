import pytest

from pkg.job import TRANSITIONS, Job, JobStatus, TransitionRefused

__all__ = ["TRANSITIONS", "TransitionRefused", "pytest"]


def test_queued_start_runs() -> None:
    job = Job()
    job.status = JobStatus.QUEUED
    job.apply("start")


def test_running_finish_is_done() -> None:
    job = Job()
    job.status = JobStatus.RUNNING
    job.apply("finish")


@pytest.mark.parametrize(
    ("state", "event"),
    [
        pytest.param(JobStatus.QUEUED, "finish", id="queued-finish"),
        pytest.param(JobStatus.RUNNING, "start", id="running-start"),
        pytest.param(JobStatus.DONE, "start", id="done-start"),
        pytest.param(JobStatus.DONE, "finish", id="done-finish"),
    ],
)
def test_an_illegal_cell_is_refused(state: JobStatus, event: str) -> None:
    job = Job()
    job.status = state
    with pytest.raises(TransitionRefused):
        job.apply(event)
