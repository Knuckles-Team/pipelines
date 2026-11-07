use jobs::{Job, JobStatus, TransitionRefused, TRANSITIONS};

#[test]
fn queued_start_runs() {
    let mut job = Job { status: JobStatus::Queued };
    assert!(job.apply("start").is_ok());
}

#[test]
fn running_finish_is_done() {
    let mut job = Job { status: JobStatus::Running };
    assert!(job.apply("finish").is_ok());
}
