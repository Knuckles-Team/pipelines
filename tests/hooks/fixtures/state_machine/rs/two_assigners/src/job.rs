#[derive(Clone, Copy, PartialEq, Eq)]
pub enum JobStatus {
    Queued,
    Running,
    Done,
}

pub struct TransitionRefused;

pub const INITIAL: JobStatus = JobStatus::Queued;
pub const TERMINALS: &[JobStatus] = &[JobStatus::Done];
pub const TRANSITIONS: &[(JobStatus, &str, JobStatus)] = &[
    (JobStatus::Queued, "start", JobStatus::Running),
    (JobStatus::Running, "finish", JobStatus::Done),
];

pub struct Job {
    pub status: JobStatus,
}

impl Job {
    pub fn apply(&mut self, event: &str) -> Result<(), TransitionRefused> {
        let next = TRANSITIONS
            .iter()
            .find(|(from, on, _)| *from == self.status && *on == event)
            .map(|row| row.2)
            .ok_or(TransitionRefused)?;
        self.status = next;
        Ok(())
    }
}

pub fn reset(job: &mut Job) {
    job.status = JobStatus::Queued;
}
