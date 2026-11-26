"""Run ordered release phases with a full delay between them.

``pipelines-hook release-phases run`` reads two JSON files: the ordered
candidate export of the repository-manager (readiness, fleet order, and each
project's predecessors and pinned commit and digest) and a phase policy. The
policy is validated before anything runs. It declares which phase owns each
project, each project's bump argv (and optional publication and hosted-CI
argv), and each phase's ``delay_seconds`` and ``timeout_seconds``. The
repository-manager keeps the authority over the fleet order; this module only
refuses a policy that contradicts it.

The delay of a phase starts, on a monotonic clock, once every predecessor
project completed its bump, publication and required hosted CI. A failed,
timed-out or cancelled stage stops all downstream work and keeps completed
effects. A resumed run (``--resume RUN_ID``) revalidates the prior receipts,
skips completed projects and waits a fresh full delay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pipelines_hooks.core.bounded_json import read_bounded_json
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.release.phase_events import EVENT_VERSION, ProgressHub, RunSets

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_INPUT_BYTES = 2_000_000
_STAGES = ("bump", "publish", "ci")
_POLL_SECONDS = 0.02


def load_json(path: str | Path, what: str) -> Any:
    """Read one bounded JSON input; an unreadable file cannot run."""
    try:
        return read_bounded_json(Path(path), _MAX_INPUT_BYTES, what=what, error=CannotRun)
    except OSError as exc:
        raise CannotRun(f"{what} is unavailable: {path}") from exc


def digest(payload: object) -> str:
    """The sha256 of the canonical JSON spelling."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProjectSpec:
    """One project: its stage commands and the owner inventory's pinned data."""

    project: str
    phase: str
    predecessors: tuple[str, ...]
    source_commit: str
    artifact_digest: str
    stages: tuple[tuple[str, tuple[str, ...]], ...]
    cwd: str = "."


@dataclass(frozen=True)
class Phase:
    """One phase; ``delay_seconds`` is waited before it starts, after its predecessors qualify."""

    name: str
    projects: tuple[str, ...]
    delay_seconds: float
    timeout_seconds: float


@dataclass(frozen=True)
class ReleasePhasePolicy:
    """The validated phase plan: unique membership, owner order, delays and timeouts."""

    phases: tuple[Phase, ...]
    projects: Mapping[str, ProjectSpec]
    fleet_order: tuple[str, ...]
    digest: str = ""

    def phase_of(self, project: str) -> Phase:
        return next(phase for phase in self.phases if project in phase.projects)

    def to_payload(self) -> dict[str, Any]:
        return {
            "phases": [[p.name, list(p.projects), p.delay_seconds, p.timeout_seconds] for p in self.phases],
            "projects": {
                name: [spec.predecessors, spec.source_commit, spec.artifact_digest, spec.stages, spec.cwd]
                for name, spec in sorted(self.projects.items())
            },
            "order": list(self.fleet_order),
        }


def _number(value: object, what: str, *, positive: bool, problems: list[str]) -> float:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if not ok or value < 0 or (positive and value == 0):  # type: ignore[operator]
        problems.append(f"{what} must be a finite {'positive' if positive else 'nonnegative'} number")
        return 0.0
    return float(value)  # type: ignore[arg-type]


def _inventory_problems(raw: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    problems: list[str] = []
    readiness = raw.get("readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not True:
        raise CannotRun("repository-manager readiness is unavailable or not ready; no phase may run")
    entries: dict[str, Mapping[str, Any]] = {}
    for entry in raw.get("candidates", []):
        name = str(entry.get("component_id", ""))
        if name in entries:
            problems.append(f"{name}: duplicate candidate")
        entries[name] = entry
        if not _COMMIT_RE.match(str(entry.get("source_commit", ""))):
            problems.append(f"{name}: missing pinned source commit")
        if not _DIGEST_RE.match(str(entry.get("artifact_digest", ""))):
            problems.append(f"{name}: missing pinned artifact digest")
    order = list(raw.get("order", []))
    if sorted(order) != sorted(entries) or len(order) != len(set(order)):
        problems.append("fleet order is not a permutation of the candidates")
    position = {name: index for index, name in enumerate(order)}
    for name, entry in entries.items():
        for predecessor in entry.get("predecessors", []):
            if predecessor not in entries or position.get(predecessor, 0) > position.get(name, 0):
                problems.append(f"{name}: predecessor {predecessor} violates the fleet order")
    return entries, problems


def _membership_problems(raw_phases: Sequence[Mapping[str, Any]], entries: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    owner: dict[str, int] = {}
    for index, phase in enumerate(raw_phases):
        for project in phase.get("projects", []):
            if project in owner:
                problems.append(f"{project}: duplicate phase membership")
            owner[project] = index
            if project not in entries:
                problems.append(f"{project}: not in the owner inventory")
    problems.extend(f"{name}: not in any phase" for name in sorted(set(entries) - set(owner)))
    for name, entry in entries.items():
        for predecessor in entry.get("predecessors", []):
            if name in owner and predecessor in owner and owner[predecessor] >= owner[name]:
                problems.append(f"{name}: predecessor {predecessor} is not in an earlier phase")
    return problems


def _stages(project: str, spec: Mapping[str, Any], problems: list[str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    stages = []
    for stage in _STAGES:
        argv = spec.get(f"{stage}_argv")
        if argv is None and stage != "bump":
            continue
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
            problems.append(f"{project}: {stage}_argv must be a nonempty list of strings")
            continue
        stages.append((stage, tuple(argv)))
    return tuple(stages)


def build_policy(policy: Mapping[str, Any], inventory: Mapping[str, Any]) -> ReleasePhasePolicy:
    """Validate the policy against the owner inventory; refuse before any mutation."""
    entries, problems = _inventory_problems(inventory)
    raw_phases = policy.get("phases", [])
    problems.extend(_membership_problems(raw_phases, entries))
    phases: list[Phase] = []
    for index, raw in enumerate(raw_phases):
        name = str(raw.get("name", ""))
        delay = _number(raw.get("delay_seconds", 0), f"{name} delay_seconds", positive=False, problems=problems)
        timeout = _number(raw.get("timeout_seconds"), f"{name} timeout_seconds", positive=True, problems=problems)
        if index == 0 and delay:
            problems.append(f"{name}: the first phase has no predecessor to wait for")
        phases.append(Phase(name, tuple(raw.get("projects", [])), delay, timeout))
    if len({phase.name for phase in phases}) != len(phases):
        problems.append("duplicate phase name")
    specs: dict[str, ProjectSpec] = {}
    for name, entry in entries.items():
        declared = policy.get("projects", {}).get(name)
        if not isinstance(declared, dict):
            problems.append(f"{name}: no project policy")
            continue
        phase = next((p.name for p in phases if name in p.projects), "")
        specs[name] = ProjectSpec(
            name,
            phase,
            tuple(entry.get("predecessors", [])),
            str(entry.get("source_commit", "")),
            str(entry.get("artifact_digest", "")),
            _stages(name, declared, problems),
            str(declared.get("cwd", ".")),
        )
    if problems:
        raise CannotRun("release phase policy refused: " + "; ".join(sorted(set(problems))))
    built = ReleasePhasePolicy(tuple(phases), specs, tuple(inventory["order"]))
    return ReleasePhasePolicy(built.phases, built.projects, built.fleet_order, digest(built.to_payload()))


class Clock(Protocol):
    """A monotonic clock that can wait."""

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True)
class StageResult:
    """The outcome of one stage command: ok, failed, timeout or cancelled."""

    status: str
    detail: str = ""


class Executor(Protocol):
    def run_stage(
        self, spec: ProjectSpec, stage: str, argv: Sequence[str], timeout: float, cancel: threading.Event
    ) -> StageResult: ...


class SubprocessExecutor:
    """Run one stage argv in the project's directory under a monotonic timeout."""

    def __init__(self, root: Path, clock: Clock) -> None:
        self._root = root
        self._clock = clock

    def run_stage(
        self, spec: ProjectSpec, stage: str, argv: Sequence[str], timeout: float, cancel: threading.Event
    ) -> StageResult:
        try:
            child = subprocess.Popen(list(argv), cwd=self._root / spec.cwd)  # noqa: S603
        except OSError as exc:
            return StageResult("failed", f"cannot start {stage}: {exc}")
        started = self._clock.monotonic()
        while child.poll() is None:
            if cancel.is_set():
                return self._stop(child, "cancelled")
            if self._clock.monotonic() - started > timeout:
                return self._stop(child, "timeout")
            self._clock.sleep(_POLL_SECONDS)
        return StageResult("ok" if child.returncode == 0 else "failed", f"{stage} exited {child.returncode}")

    @staticmethod
    def _stop(child: subprocess.Popen[bytes], status: str) -> StageResult:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        return StageResult(status, f"stage stopped: {status}")


class RunState:
    """The durable receipts of completed projects, bound to one run and policy."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any] | None:
        return load_json(self.path, "run state") if self.path.is_file() else None

    def save(self, record: Mapping[str, Any]) -> None:
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(record, sort_keys=True, indent=2), encoding="utf-8")
        temporary.replace(self.path)


@dataclass
class RunReport:
    """The evidence of one run; ``status`` is completed, failed or cancelled."""

    run_id: str
    policy_digest: str
    status: str = "completed"
    waits: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""
    sets: dict[str, list[str]] = field(default_factory=dict)
    last_sequence: int = 0

    def evidence(self) -> dict[str, Any]:
        return {
            "version": EVENT_VERSION,
            "kind": "evidence",
            "run_id": self.run_id,
            "policy_digest": self.policy_digest,
            "status": self.status,
            "detail": self.detail,
            "waits": self.waits,
            "sets": self.sets,
            "unstarted": self.sets.get("remaining", []),
            "last_sequence": self.last_sequence,
            "observation": "authoritative final state; an event stream may show sequence gaps",
        }


class PhaseRunner:
    """Walk the phases in order, wait each delay, and stop at the first non-ok stage."""

    def __init__(
        self,
        policy: ReleasePhasePolicy,
        *,
        run_id: str,
        hub: ProgressHub,
        clock: Clock,
        executor: Executor,
        state: RunState,
        cancel: threading.Event,
        resume: bool = False,
    ) -> None:
        self._policy, self._hub, self._clock = policy, hub, clock
        self._executor, self._state, self._cancel = executor, state, cancel
        self._run_id, self._resume = run_id, resume
        self._record: dict[str, Any] = {"run_id": run_id, "policy_digest": policy.digest, "completed": {}}
        self._qualified_at = 0.0

    def _open_state(self) -> None:
        prior = self._state.load()
        if prior is None:
            if self._resume:
                raise CannotRun(f"cannot resume {self._run_id}: no prior state")
            self._state.save(self._record)
            return
        if not self._resume:
            raise CannotRun("a prior run state exists; resume it with --resume or choose a new state path")
        if prior.get("run_id") != self._run_id or prior.get("policy_digest") != self._policy.digest:
            raise CannotRun("resume refused: the prior run or policy digest differs")
        completed = prior.get("completed", {})
        for name, receipt in completed.items():
            spec = self._policy.projects.get(name)
            if spec is None or receipt.get("artifact_digest") != spec.artifact_digest:
                raise CannotRun(f"resume refused: receipt of {name} does not bind the pinned artifact digest")
            if any(predecessor not in completed for predecessor in spec.predecessors):
                raise CannotRun(f"resume refused: {name} completed without its predecessors")
            self._hub.sets.mark_completed(name)
        self._record = prior

    def run(self) -> RunReport:
        report = RunReport(self._run_id, self._policy.digest)
        self._open_state()
        self._qualified_at = self._clock.monotonic()
        self._hub.emit("run-start")
        for index, phase in enumerate(self._policy.phases):
            todo = [name for name in phase.projects if name not in self._record["completed"]]
            if todo and index > 0 and not self._wait(phase, report):
                break
            if not self._run_phase(phase, todo, report):
                break
        self._hub.sets.check()
        report.sets, report.last_sequence = self._hub.sets.snapshot(), self._hub.sequence
        self._hub.emit("run-end", status=report.status)
        return report

    def _wait(self, phase: Phase, report: RunReport) -> bool:
        started = self._qualified_at
        self._hub.emit("phase-wait-start", phase=phase.name, delay_seconds=phase.delay_seconds)
        while self._clock.monotonic() - started < phase.delay_seconds:
            if self._cancel.is_set():
                report.status, report.detail = "cancelled", f"cancelled while waiting before {phase.name}"
                return False
            remaining = phase.delay_seconds - (self._clock.monotonic() - started)
            self._clock.sleep(min(max(remaining, 0.0), _POLL_SECONDS))
        ended = self._clock.monotonic()
        report.waits.append(
            {
                "phase": phase.name,
                "delay_seconds": phase.delay_seconds,
                "monotonic_start": started,
                "monotonic_end": ended,
                "elapsed": ended - started,
            }
        )
        self._hub.emit("phase-wait-end", phase=phase.name, elapsed=ended - started)
        return True

    def _run_phase(self, phase: Phase, todo: list[str], report: RunReport) -> bool:
        for name in todo:
            self._hub.transition(name, "active", phase=phase.name)
            stage, result = self._run_project(self._policy.projects[name], phase)
            if result.status != "ok":
                final = "cancelled" if result.status == "cancelled" else "failed"
                self._hub.transition(name, final, phase=phase.name)
                report.status, report.detail = final, f"{name} {stage}: {result.detail}"
                return False
            self._complete(name)
            self._hub.transition(name, "completed", phase=phase.name)
            self._qualified_at = self._clock.monotonic()
        return True

    def _run_project(self, spec: ProjectSpec, phase: Phase) -> tuple[str, StageResult]:
        result = StageResult("ok")
        for stage, argv in spec.stages:
            if self._cancel.is_set():
                return stage, StageResult("cancelled", "cancelled before the stage")
            self._hub.emit("stage-begin", phase=phase.name, project=spec.project, stage=stage)
            result = self._executor.run_stage(spec, stage, argv, phase.timeout_seconds, self._cancel)
            self._hub.emit("stage-end", phase=phase.name, project=spec.project, stage=stage, status=result.status)
            if result.status != "ok":
                return stage, result
        return "", result

    def _complete(self, name: str) -> None:
        spec = self._policy.projects[name]
        self._record["completed"][name] = {
            "source_commit": spec.source_commit,
            "artifact_digest": spec.artifact_digest,
            "stages": [stage for stage, _ in spec.stages],
        }
        self._state.save(self._record)


def _run_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    policy = build_policy(
        load_json(args.policy, "phase policy"), load_json(args.candidates, "ordered candidate export")
    )
    if args.major_upgrade:
        from pipelines_hooks.release.major_upgrade import admit_from_arguments

        code = admit_from_arguments(args, root)
        if code:
            return code
    clock = SystemClock()
    hub = ProgressHub(args.run_id, RunSets(policy.projects))
    stream = hub.subscribe()
    cancel = threading.Event()
    previous = [signal.signal(sig, lambda *_: cancel.set()) for sig in (signal.SIGINT, signal.SIGTERM)]
    runner = PhaseRunner(
        policy,
        run_id=args.run_id,
        hub=hub,
        clock=clock,
        executor=SubprocessExecutor(root, clock),
        state=RunState(Path(args.state)),
        cancel=cancel,
        resume=args.resume,
    )
    try:
        report = runner.run()
    finally:
        for sig, handler in zip((signal.SIGINT, signal.SIGTERM), previous, strict=True):
            signal.signal(sig, handler)
    for event in stream.drain():
        print(json.dumps(event, sort_keys=True), flush=True)
    print(json.dumps(report.evidence(), sort_keys=True), flush=True)
    return 0 if report.status == "completed" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="release-phases", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the ordered phases")
    run.add_argument("--root", default=".", help="directory the project cwd values are relative to")
    run.add_argument("--policy", required=True)
    run.add_argument("--candidates", required=True, help="repository-manager ordered candidate export")
    run.add_argument("--state", required=True, help="durable run state file")
    run.add_argument("--run-id", required=True)
    run.add_argument("--resume", action="store_true", help="resume the run bound to --run-id")
    run.add_argument("--major-upgrade", help="major upgrade candidate file admitted before any bump")
    run.add_argument("--owner-inventory")
    run.add_argument("--receipts", help="Scion SDK compatibility receipts")
    run.add_argument("--report")
    pin = sub.add_parser("pin", help="admit and apply a major dependency upgrade")
    pin.add_argument("--root", default=".")
    pin.add_argument("--major-upgrade", required=True)
    pin.add_argument("--owner-inventory", required=True)
    pin.add_argument("--receipts")
    pin.add_argument("--report", required=True)
    pin.add_argument("--resume", action="store_true")
    return parser


def main(argv: list[str]) -> int:
    """Entry of ``pipelines-hook release-phases``."""
    args = _parser().parse_args(argv)
    if args.command == "pin":
        from pipelines_hooks.release.major_upgrade import admit_from_arguments

        return admit_from_arguments(args, Path(args.root).resolve())
    return _run_command(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
