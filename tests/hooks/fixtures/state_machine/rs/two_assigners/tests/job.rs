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
fn every_missing_cell_is_refused() {
    for state in [JobStatus::Queued, JobStatus::Running, JobStatus::Done] {
        for event in ["start", "finish"] {
            if !TRANSITIONS.iter().any(|(from, on, _)| *from == state && *on == event) {
                let mut job = Job { status: state };
                assert!(matches!(job.apply(event), Err(TransitionRefused)));
            }
        }
    }
}
