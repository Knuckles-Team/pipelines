use crate::job::Job;

pub fn is_done(job: &Job) -> bool {
    job.status == "done"
}
