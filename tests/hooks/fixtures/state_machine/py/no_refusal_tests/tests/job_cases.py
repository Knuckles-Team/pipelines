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
