from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"


class TransitionRefused(Exception):
    pass


INITIAL = JobStatus.QUEUED
TERMINALS = (JobStatus.DONE,)
TRANSITIONS = {
    (JobStatus.QUEUED, "start"): JobStatus.RUNNING,
    (JobStatus.RUNNING, "finish"): JobStatus.DONE,
}


class Job:
    status: JobStatus

    def apply(self, event: str) -> None:
        target = TRANSITIONS.get((self.status, event))
        if target is None:
            raise TransitionRefused(event)
        self.status = target
