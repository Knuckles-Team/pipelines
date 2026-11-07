import itertools

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


def test_every_missing_cell_is_refused() -> None:
    for state, event in itertools.product(JobStatus, ["start", "finish"]):
        if (state, event) not in TRANSITIONS:
            job = Job()
            job.status = state
            with pytest.raises(TransitionRefused):
                job.apply(event)
