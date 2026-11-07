"""PIPE-GATES-R086.3: the Rust reader builds ``Machine`` records from a tree-sitter tree."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from pipelines_hooks.code.state_machine_model import Machine
from pipelines_hooks.code.state_machine_rs import loose_sites, read_rust
from pipelines_hooks.core.errors import CannotRun

ENUM = """
pub enum JobStatus { Queued, Running, Done }
pub struct TransitionRefused;
"""


def _read(source: str, path: str = "crates/jobs/src/job.rs") -> list[Machine]:
    return read_rust(path, textwrap.dedent(ENUM + source))


def _job(source: str) -> Machine:
    (machine,) = [m for m in _read(source) if m.type_name == "Job"]
    return machine


@pytest.mark.spec("PIPE-GATES-R086.3")
def test_rust_reader_recognises_a_const_edge_table() -> None:
    machine = _job(
        """
        pub const TRANSITIONS: &[(JobStatus, &str, JobStatus)] = &[
            (JobStatus::Queued, "start", JobStatus::Running),
            (JobStatus::Running, "finish", JobStatus::Done),
        ];
        pub const INITIAL: JobStatus = JobStatus::Queued;
        pub const TERMINALS: &[JobStatus] = &[JobStatus::Done];
        pub struct Job { status: JobStatus, started_at: Option<u64>, finished_at: Option<u64> }
        """
    )
    assert machine.table == "TRANSITIONS"
    assert machine.edges == (("Queued", "start", "Running"), ("Running", "finish", "Done"))
    assert (machine.initial, machine.terminals) == ("Queued", ("Done",))
    assert machine.states == ("Queued", "Running", "Done")
    assert machine.status_kind == "enum"
    assert machine.flags == ("started_at", "finished_at")


@pytest.mark.spec("PIPE-GATES-R086.3")
def test_rust_reader_recognises_an_apply_returning_a_refusal() -> None:
    machine = _job(
        """
        pub struct Job { status: JobStatus }
        impl Job {
            pub fn apply(&mut self, event: &str) -> Result<(), TransitionRefused> {
                self.status = JobStatus::Running;
                Ok(())
            }
        }
        """
    )
    assert (machine.function, machine.refusal) == ("Job.apply", "TransitionRefused")
    assert [s.function for s in machine.assigners] == ["Job.apply"]


@pytest.mark.spec("PIPE-GATES-R086.3")
def test_rust_self_receiver_resolves_to_the_impl_type() -> None:
    machines = _read(
        """
        pub struct Job { status: String }
        pub struct Task { status: String }
        impl Task {
            fn start(&mut self) { self.status = "running".into(); }
            fn done(&self) -> bool { self.status == "done" }
        }
        """
    )
    by_name = {m.type_name: m for m in machines}
    assert by_name["Job"].assigners == [] and by_name["Job"].status_kind == "string"
    assert [s.function for s in by_name["Task"].assigners] == ["Task.start"]
    assert [s.function for s in by_name["Task"].string_compares] == ["Task.done"]


@pytest.mark.spec("PIPE-GATES-R086.3")
def test_rust_struct_update_counts_as_an_assignment() -> None:
    source = """
    pub struct Job { status: JobStatus, id: u32 }
    fn finish(job: Job) -> Job { Job { status: JobStatus::Done, ..job } }
    fn reset(job: &mut Job) { std::mem::replace(&mut job.status, JobStatus::Queued); }
    fn bump(job: &mut Job) { job.status = JobStatus::Running; }
    """
    machine = _job(source)
    assert sorted(s.function for s in machine.assigners) == ["bump", "finish", "reset"]
    loose = loose_sites("crates/jobs/src/job.rs", textwrap.dedent(ENUM + source))
    assert sorted(u.site.function for u in loose) == ["bump", "reset"]


@pytest.mark.spec("PIPE-GATES-R086.3")
def test_rust_cfg_test_module_is_skipped() -> None:
    machines = _read(
        """
        pub struct Job { status: String }
        #[cfg(test)]
        mod tests {
            pub struct Fixture { status: String }
            fn poke(job: &mut super::Job) { job.status = "x".into(); }
        }
        """
    )
    assert [m.type_name for m in machines] == ["Job"]
    assert machines[0].assigners == []
    assert _read("pub struct Job { status: String }", "crates/jobs/tests/job.rs") == []
    assert _read("pub struct Job { status: String }", "target/debug/build/job.rs") == []


@pytest.mark.spec("PIPE-GATES-R086.3")
def test_rust_parse_error_exits_two() -> None:
    with pytest.raises(CannotRun, match="does not parse"):
        read_rust("crates/jobs/src/job.rs", "pub struct Job { status: ")


#: A large file: hundreds of struct, impl and cfg(test) items, as in a big crate module.
_LARGE = "pub enum JobStatus { Queued, Running, Done }\\nfor i in range(400):\\n    pass\\n"


@pytest.mark.spec("PIPE-GATES-R086.3")
def test_rust_reader_survives_a_large_file_in_a_fresh_process() -> None:
    """The process exits cleanly after reading a large file (tree-sitter 0.26.0 crashed at collection)."""
    script = textwrap.dedent(
        """
        import gc
        from pipelines_hooks.code.state_machine_rs import read_rust

        parts = ["pub enum JobStatus { Queued, Running, Done }\\n"]
        for i in range(400):
            parts.append(
                f"#[derive(Debug, Clone)]\\n#[serde(rename_all = \\"snake_case\\")]\\n"
                f"pub struct Job{i} {{ status: JobStatus, started_at: Option<u64>, finished_at: Option<u64> }}\\n"
                f"impl Job{i} {{\\n pub fn apply(&mut self) -> Result<(), TransitionRefused> "
                f"{{ self.status = JobStatus::Running; Ok(()) }}\\n"
                f" fn reset(&mut self) {{ if self.status == \\"done\\" {{ self.status = JobStatus::Queued; }} }}\\n}}\\n"
            )
        tests = "".join(f"    #[test]\\n    fn t{i}() {{ assert_eq!({i}, {i}); }}\\n" for i in range(400))
        parts.append("#[cfg(test)]\\nmod tests {\\n" + tests + "}\\n")
        machines = read_rust("crates/x/src/lib.rs", "".join(parts))
        gc.collect()
        print(len(machines))
        """
    )
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip() == "400"
