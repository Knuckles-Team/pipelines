from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"


class TransitionRefused(Exception):
    pass


INITIAL = JobStatus.QUEUED
TERMINALS = (JobStatus.DONE,)
TRANSITIONS = [
    (JobStatus.QUEUED, "start", JobStatus.RUNNING),
    (JobStatus.QUEUED, "start", JobStatus.DONE),
    (JobStatus.RUNNING, "finish", JobStatus.DONE),
]


class Job:
    status: JobStatus

    def apply(self, event: str) -> None:
        target = next((to for frm, ev, to in TRANSITIONS if (frm, ev) == (self.status, event)), None)
        if target is None:
            raise TransitionRefused(event)
        self.status = target
