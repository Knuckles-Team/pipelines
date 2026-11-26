"""PIPE-RELEASE-R001.1--R001.6: ordered release phases with delays and live progress."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.release.phase_events import SUBSCRIBER_CAPACITY, ProgressHub, RunSets
from pipelines_hooks.release.phases import (
    PhaseRunner,
    ProjectSpec,
    RunState,
    StageResult,
    build_policy,
)

COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64


def _inventory(names: list[str], predecessors: dict[str, list[str]] | None = None) -> dict[str, Any]:
    predecessors = predecessors or {}
    return {
        "schema": "release-candidates/1",
        "readiness": {"ready": True},
        "order": names,
        "candidates": [
            {
                "component_id": name,
                "predecessors": predecessors.get(name, []),
                "source_commit": COMMIT,
                "artifact_digest": DIGEST,
            }
            for name in names
        ],
    }


def _policy(phases: list[tuple[list[str], float]], argv: dict[str, list[str]] | None = None) -> dict[str, Any]:
    names = [name for members, _ in phases for name in members]
    return {
        "phases": [
            {"name": f"P{i + 1}", "projects": members, "delay_seconds": delay if i else 0, "timeout_seconds": 30}
            for i, (members, delay) in enumerate(phases)
        ],
        "projects": {name: {"bump_argv": (argv or {}).get(name, ["true"])} for name in names},
    }


class FakeClock:
    """A controlled monotonic clock: sleeping advances it, nothing waits."""

    def __init__(self) -> None:
        self.now = 100.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeExecutor:
    """Records every stage; advances the clock by a configured duration."""

    def __init__(self, clock: FakeClock, *, duration: float = 0.5, outcomes: dict[str, str] | None = None) -> None:
        self.clock, self.duration, self.outcomes = clock, duration, outcomes or {}
        self.calls: list[tuple[str, str, float]] = []

    def run_stage(self, spec: ProjectSpec, stage: str, argv, timeout, cancel) -> StageResult:  # type: ignore[no-untyped-def]
        self.clock.now += self.duration
        self.calls.append((spec.project, stage, self.clock.now))
        return StageResult(self.outcomes.get(spec.project, "ok"), "fake")


def _runner(tmp_path: Path, policy, clock=None, executor=None, *, cancel=None, resume=False, run_id="run-1"):  # type: ignore[no-untyped-def]
    clock = clock or FakeClock()
    hub = ProgressHub(run_id, RunSets(policy.projects))
    runner = PhaseRunner(
        policy,
        run_id=run_id,
        hub=hub,
        clock=clock,
        executor=executor or FakeExecutor(clock),
        state=RunState(tmp_path / "state.json"),
        cancel=cancel or threading.Event(),
        resume=resume,
    )
    return runner, hub


def _dir(parent: Path, name: str) -> Path:
    path = parent / name
    path.mkdir()
    return path


def _three_in_two_phases():  # type: ignore[no-untyped-def]
    inventory = _inventory(["a", "b", "c"], {"c": ["a", "b"]})
    return build_policy(_policy([(["a", "b"], 0), (["c"], 5)]), inventory)


# spec: PIPE-RELEASE-R001.1
def test_release_phase_progress_model(tmp_path: Path) -> None:
    policy = _three_in_two_phases()
    assert [(p.name, p.projects, p.delay_seconds, p.timeout_seconds) for p in policy.phases] == [
        ("P1", ("a", "b"), 0.0, 30.0),
        ("P2", ("c",), 5.0, 30.0),
    ]
    assert policy.projects["c"].predecessors == ("a", "b")
    assert policy.projects["a"].stages == (("bump", ("true",)),)
    assert policy.digest.startswith("sha256:")
    runner, hub = _runner(tmp_path, policy)
    subscriber = hub.subscribe()
    runner.run()
    events = subscriber.drain()
    assert all(
        {"version", "run_id", "sequence", "phase", "project", "sets"} <= set(event) and event["version"] == 1
        for event in events
    )
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert SUBSCRIBER_CAPACITY == 256
    for invalid in (-1, float("inf"), float("nan"), True, "1"):
        bad = _policy([(["a", "b"], 0), (["c"], invalid)])  # type: ignore[arg-type]
        with pytest.raises(CannotRun, match="finite nonnegative"):
            build_policy(bad, _inventory(["a", "b", "c"], {"c": ["a", "b"]}))


# spec: PIPE-RELEASE-R001.2
def test_release_phase_progress_behavior(tmp_path: Path) -> None:
    clock = FakeClock()
    executor = FakeExecutor(clock, duration=0.5)
    runner, hub = _runner(tmp_path, _three_in_two_phases(), clock, executor)
    subscriber = hub.subscribe()
    report = runner.run()
    assert report.status == "completed"
    (wait,) = report.waits
    # the full delay starts after the final predecessor's last stage, not before
    assert wait["monotonic_start"] == executor.calls[1][2]
    assert wait["elapsed"] >= 5.0
    assert executor.calls[2][2] - executor.calls[1][2] >= 5.0
    transitions = [
        (e["event"], e["project"], e["to"]) for e in subscriber.drain() if e["event"].startswith("transition")
    ]
    assert transitions[:2] == [("transition-begin", "a", "active"), ("transition-end", "a", "active")]
    assert ("transition-end", "c", "completed") in transitions

    # failure stops downstream work and keeps completed effects
    failing_clock = FakeClock()
    failing = FakeExecutor(failing_clock, outcomes={"b": "failed"})
    runner, hub = _runner(_dir(tmp_path, "f"), _three_in_two_phases(), failing_clock, failing)
    report = runner.run()
    assert report.status == "failed"
    assert [call[0] for call in failing.calls] == ["a", "b"]
    assert report.sets["completed"] == ["a"] and report.sets["failed"] == ["b"] and report.sets["remaining"] == ["c"]

    # a restarted run revalidates its receipts and waits a fresh full delay
    resumed_clock = FakeClock()
    resumed = FakeExecutor(resumed_clock, duration=0.0)
    first, _ = _runner(
        _dir(tmp_path, "r"), _three_in_two_phases(), FakeClock(), FakeExecutor(FakeClock(), outcomes={"b": "failed"})
    )
    first.run()
    runner, _ = _runner(tmp_path / "r", _three_in_two_phases(), resumed_clock, resumed, resume=True)
    again = runner.run()
    assert again.status == "completed"
    assert [call[0] for call in resumed.calls][0] == "b"
    assert "a" not in [call[0] for call in resumed.calls]
    assert again.waits[0]["elapsed"] >= 5.0


# spec: PIPE-RELEASE-R001.3
def test_release_phase_progress_wiring(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from pipelines_hooks.cli import GATES, main as cli_main

    assert GATES["release-phases"] == "pipelines_hooks.release.phases"
    files = _write_files(_dir(tmp_path, "w"), [(["a"], 0), (["b"], 0)], {"b": ["a"]})
    code = cli_main(["release-phases", "run", *files])
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert code == 0
    assert lines[-1]["kind"] == "evidence" and lines[-1]["status"] == "completed"
    assert all(line["version"] == 1 for line in lines)

    not_ready = _inventory(["a"])
    not_ready["readiness"] = {"ready": False}
    with pytest.raises(CannotRun, match="readiness"):
        build_policy(_policy([(["a"], 0)]), not_ready)
    del not_ready["readiness"]
    with pytest.raises(CannotRun, match="readiness"):
        build_policy(_policy([(["a"], 0)]), not_ready)

    runner, hub = _runner(_dir(tmp_path, "slow"), build_policy(_policy([(["a"], 0)]), _inventory(["a"])))
    slow = hub.subscribe(capacity=3)
    runner.run()
    drained = slow.drain()
    assert drained[-1]["kind"] == "gap" and not slow.connected
    assert drained[-1]["next_sequence"] == drained[-2]["sequence"] + 1
    snapshot = slow.resume()
    assert snapshot["kind"] == "snapshot" and snapshot["sequence"] == hub.sequence and slow.connected


def _write_files(tmp_path: Path, phases, predecessors=None, argv=None) -> list[str]:  # type: ignore[no-untyped-def]
    names = [name for members, _ in phases for name in members]
    for filename, payload in (
        ("policy.json", _policy(phases, argv)),
        ("candidates.json", _inventory(names, predecessors)),
    ):
        (tmp_path / filename).write_text(json.dumps(payload), encoding="utf-8")
    return [
        "--root", str(tmp_path),
        "--policy", str(tmp_path / "policy.json"),
        "--candidates", str(tmp_path / "candidates.json"),
        "--state", str(tmp_path / "state.json"),
        "--run-id", "run-1",
    ]  # fmt: skip


# spec: PIPE-RELEASE-R001.4
def test_release_phase_progress_refusal(tmp_path: Path) -> None:
    inventory = _inventory(["a", "b", "c"], {"c": ["a", "b"]})
    refusals = {
        "duplicate phase membership": _policy([(["a", "b"], 0), (["b", "c"], 1)]),
        "not in an earlier phase": _policy([(["c"], 0), (["a", "b"], 1)]),
        "delay_seconds": _policy([(["a", "b"], 0), (["c"], -1)]),
    }
    for message, policy in refusals.items():
        with pytest.raises(CannotRun, match=message):
            build_policy(policy, inventory)
    missing = _inventory(["a", "b", "c"], {"c": ["a", "b"]})
    del missing["candidates"][0]["artifact_digest"]
    with pytest.raises(CannotRun, match="missing pinned artifact digest"):
        build_policy(_policy([(["a", "b"], 0), (["c"], 1)]), missing)
    wrong_order = _inventory(["c", "a", "b"], {"c": ["a", "b"]})
    with pytest.raises(CannotRun, match="violates the fleet order"):
        build_policy(_policy([(["a", "b"], 0), (["c"], 1)]), wrong_order)

    # a timeout stops downstream publication
    clock = FakeClock()
    executor = FakeExecutor(clock, outcomes={"a": "timeout"})
    runner, _ = _runner(_dir(tmp_path, "t"), _three_in_two_phases(), clock, executor)
    assert runner.run().status == "failed"
    assert [call[0] for call in executor.calls] == ["a"]

    # cancellation before the first stage runs nothing
    flag = threading.Event()
    flag.set()
    clock = FakeClock()
    executor = FakeExecutor(clock)
    runner, _ = _runner(_dir(tmp_path, "c"), _three_in_two_phases(), clock, executor, cancel=flag)
    cancelled = runner.run()
    assert cancelled.status == "cancelled" and executor.calls == []

    # resume binds the prior run and the pinned artifact digests
    store = tmp_path / "bind"
    store.mkdir()
    runner, _ = _runner(store, _three_in_two_phases(), executor=FakeExecutor(FakeClock(), outcomes={"b": "failed"}))
    runner.run()
    with pytest.raises(CannotRun, match="prior run state exists"):
        _runner(store, _three_in_two_phases())[0].run()
    with pytest.raises(CannotRun, match="prior run or policy digest differs"):
        _runner(store, _three_in_two_phases(), resume=True, run_id="other")[0].run()
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    state["completed"]["a"]["artifact_digest"] = "sha256:" + "c" * 64
    (store / "state.json").write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(CannotRun, match="does not bind the pinned artifact digest"):
        _runner(store, _three_in_two_phases(), resume=True)[0].run()


# spec: PIPE-RELEASE-R001.5
def test_release_phase_progress_evidence(tmp_path: Path) -> None:
    policy = _three_in_two_phases()
    flag = threading.Event()
    clock = FakeClock()

    class CancelAfterA(FakeExecutor):
        def run_stage(self, spec, stage, argv, timeout, cancel):  # type: ignore[no-untyped-def]
            if spec.project == "b":
                flag.set()
                return StageResult("cancelled", "stopped")
            return super().run_stage(spec, stage, argv, timeout, cancel)

    runner, hub = _runner(tmp_path, policy, clock, CancelAfterA(clock), cancel=flag)
    report = runner.run()
    evidence = report.evidence()
    sets = evidence["sets"]
    assert sets == {"completed": ["a"], "active": [], "remaining": ["c"], "failed": [], "cancelled": ["b"]}
    assert evidence["unstarted"] == ["c"] and evidence["status"] == "cancelled"
    members = [name for held in sets.values() for name in held]
    assert sorted(members) == ["a", "b", "c"]
    assert evidence["policy_digest"] == policy.digest and "gaps" in evidence["observation"]
    hub.sets.check()

    c2 = FakeClock()
    ok = _runner(_dir(tmp_path, "ok"), policy, clock=c2, executor=FakeExecutor(c2))[0].run().evidence()
    (wait,) = ok["waits"]
    assert wait["delay_seconds"] == 5.0 and wait["elapsed"] == wait["monotonic_end"] - wait["monotonic_start"] >= 5.0
    assert ok["sets"]["completed"] == ["a", "b", "c"] and not ok["sets"]["remaining"]
    broken = RunSets(["a", "b"])
    broken._held["failed"].add("a")  # noqa: SLF001
    broken._held["completed"].add("a")  # noqa: SLF001
    with pytest.raises(CannotRun, match="disjoint cover"):
        broken.check()


def _cli(tmp_path: Path, extra: list[str] | None = None) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "pipelines_hooks", "release-phases", "run", *_args(tmp_path), *(extra or [])],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])},
    )


def _args(tmp_path: Path) -> list[str]:
    return [
        "--root", str(tmp_path),
        "--policy", str(tmp_path / "policy.json"),
        "--candidates", str(tmp_path / "candidates.json"),
        "--state", str(tmp_path / "state.json"),
        "--run-id", "run-1",
    ]  # fmt: skip


def _bump(tmp_path: Path, name: str, *, fail: bool = False, hang: bool = False) -> list[str]:
    code = (
        "import sys, time, pathlib\n"
        f"p = pathlib.Path({str(tmp_path)!r})\n"
        f"(p / '{name}.start').write_text(repr(time.monotonic()))\n"
        + ("time.sleep(60)\n" if hang else "")
        + f"(p / '{name}.end').write_text(repr(time.monotonic()))\n"
        + ("sys.exit(3)\n" if fail else "")
    )
    return [sys.executable, "-c", code]


def _scenario(tmp_path: Path, **kinds: bool) -> None:
    argv = {
        name: _bump(tmp_path, name, fail=kinds.get(f"fail_{name}", False), hang=kinds.get(f"hang_{name}", False))
        for name in "abc"
    }
    files = _write_files(tmp_path, [(["a", "b"], 0), (["c"], 1)], {"c": ["a", "b"]}, argv)
    assert files


def _lines(process: subprocess.Popen[str]) -> list[dict[str, Any]]:
    out, _ = process.communicate(timeout=60)
    return [json.loads(line) for line in out.splitlines()]


# spec: PIPE-RELEASE-R001.6
def test_release_phase_progress_cli(tmp_path: Path) -> None:
    ok = tmp_path / "ok"
    ok.mkdir()
    _scenario(ok)
    process = _cli(ok)
    lines = _lines(process)
    assert process.returncode == 0
    evidence = lines[-1]
    assert evidence["status"] == "completed" and evidence["sets"]["completed"] == ["a", "b", "c"]
    # real elapsed time from the final predecessor's end, measured by the bump commands themselves
    last_predecessor = max(float((ok / f"{n}.end").read_text()) for n in "ab")
    downstream = float((ok / "c.start").read_text())
    assert downstream - last_predecessor >= 1.0
    assert evidence["waits"][0]["elapsed"] >= 1.0
    seen = [event["sets"]["active"] for event in lines if event.get("kind") == "event"]
    assert ["a"] in seen and ["b"] in seen and ["c"] in seen

    failed = tmp_path / "failed"
    failed.mkdir()
    _scenario(failed, fail_a=True)
    process = _cli(failed)
    evidence = _lines(process)[-1]
    assert process.returncode == 1 and evidence["status"] == "failed"
    assert not (failed / "b.start").exists() and not (failed / "c.start").exists()

    cancelled = tmp_path / "cancelled"
    cancelled.mkdir()
    _scenario(cancelled, hang_a=True)
    process = _cli(cancelled)
    deadline = time.monotonic() + 30
    while not (cancelled / "a.start").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    process.send_signal(signal.SIGTERM)
    evidence = _lines(process)[-1]
    assert process.returncode == 1 and evidence["status"] == "cancelled"
    assert evidence["sets"]["cancelled"] == ["a"] and evidence["unstarted"] == ["b", "c"]
    assert not (cancelled / "c.start").exists()

    # a slow subscriber overflows the 256-event buffer, gets a gap, then a fresh snapshot
    names = [f"p{i}" for i in range(70)]
    big = build_policy(_policy([(names, 0)]), _inventory(names))
    clock = FakeClock()
    runner, hub = _runner(_dir(tmp_path, "big"), big, clock, FakeExecutor(clock, duration=0.0))
    slow = hub.subscribe()
    runner.run()
    queued = slow.drain()
    assert len(queued) == SUBSCRIBER_CAPACITY + 1 and queued[-1]["kind"] == "gap"
    assert queued[-1]["last_sequence"] == SUBSCRIBER_CAPACITY
    fresh = slow.resume()
    assert fresh["sequence"] == hub.sequence > SUBSCRIBER_CAPACITY
