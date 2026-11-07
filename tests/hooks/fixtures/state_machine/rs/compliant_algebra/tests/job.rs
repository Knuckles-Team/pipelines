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

#[test]
fn queued_finish_is_refused() {
    let mut job = Job { status: JobStatus::Queued };
    assert!(matches!(job.apply("finish"), Err(TransitionRefused)));
}

#[test]
fn running_start_is_refused() {
    let mut job = Job { status: JobStatus::Running };
    assert!(matches!(job.apply("start"), Err(TransitionRefused)));
}

#[test]
fn done_start_is_refused() {
    let mut job = Job { status: JobStatus::Done };
    assert!(matches!(job.apply("start"), Err(TransitionRefused)));
}

#[test]
fn done_finish_is_refused() {
    let mut job = Job { status: JobStatus::Done };
    assert!(matches!(job.apply("finish"), Err(TransitionRefused)));
}
