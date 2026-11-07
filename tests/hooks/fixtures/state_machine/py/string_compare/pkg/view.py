from pkg.job import Job


def is_done(job: Job) -> bool:
    return job.status == "done"
