"""Run a gate set against one source and record every gate's verdict.

The partition comes from the published declaration (``gate_sets``); each
gate runs through its execution binding, which the caller injects. The
runner never invents gate behavior: it dispatches, times, captures the
evidence and aggregates the verdicts. A gate in the set without a binding
fails the whole run closed, named, before any gate starts. The pipelines
published blocking gates run through their entry points; a gate the
caller environment has not bound (for example a consumer-side tool gate)
keeps the run failing closed until the environment binds it.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.settings import process_environment
from pipelines_hooks.gate_sets import GateSets, load_gate_sets, published_sets

#: One gate's execution: run it against ``source`` and report its exit
#: status with the output it produced.
Executor = Callable[[Path], tuple[int, str]]


@dataclass(frozen=True)
class GateVerdict:
    """One gate's outcome against the source."""

    gate: str
    status: int  # 0 clean, 1 findings, 2 could not run
    evidence_digest: str
    seconds: float


@dataclass(frozen=True)
class GateSetRun:
    """One set's run: its members' verdicts in declaration order."""

    set_name: str
    source: str
    verdicts: tuple[GateVerdict, ...]

    @property
    def status(self) -> int:
        """The set's verdict: the worst member status."""
        return max(verdict.status for verdict in self.verdicts)


def evidence_digest(output: str) -> str:
    """The digest of one gate run's captured evidence."""
    return "sha256:" + hashlib.sha256(output.encode("utf-8", "replace")).hexdigest()


def run_gate_on(gate: str, source: Path, executor: Executor) -> GateVerdict:
    """One gate through its binding, with the evidence captured and digested."""
    started = time.monotonic()
    status, output = executor(source)
    return GateVerdict(
        gate=gate,
        status=int(status),
        evidence_digest=evidence_digest(output),
        seconds=round(time.monotonic() - started, 3),
    )


def run_set(set_name: str, source: Path, executors: Mapping[str, Executor], sets: GateSets | None = None) -> GateSetRun:
    """Run one declared set in full; a gate without a binding fails the run first."""
    partition = sets or published_sets()
    if set_name not in ("fast", "full"):
        raise CannotRun(f"gate-set: unknown set {set_name!r}; the declaration names fast and full")
    if not source.is_dir():
        raise CannotRun(f"gate-set: source {source} is not a directory")
    gates = partition.fast if set_name == "fast" else partition.full
    unbound = [gate for gate in gates if gate not in executors]
    if unbound:
        raise CannotRun(
            f"gate-set: no execution binding for {', '.join(unbound)}; bind every gate of the set before it decides a landing"
        )
    verdicts = [run_gate_on(gate, source, executors[gate]) for gate in gates]
    return GateSetRun(set_name=set_name, source=str(source), verdicts=tuple(verdicts))


def _spawn_published(gate: str, source: Path) -> tuple[int, str]:
    """One pipelines-published gate through its entry point, output captured.

    Grouped checks take no arguments and read the working directory, so
    they run with the source as the current directory; single gates take
    the source as ``--root``.
    """
    from pipelines_hooks.cli import GROUPS

    args = [] if gate in GROUPS else ["--root", str(source)]
    result = subprocess.run(
        [sys.executable, "-m", "pipelines_hooks", gate, *args],
        cwd=str(source),
        env=process_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def _bound_published(gate: str) -> Executor:
    def run(source: Path) -> tuple[int, str]:
        return _spawn_published(gate, source)

    return run


def published_executors() -> dict[str, Executor]:
    """The pipelines-published blocking gates, run through their entry points."""
    return {gate: _bound_published(gate) for gate in ("secrets", "tests-fast", "spec", "supply-chain")}


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="gate-set", description=__doc__)
    parser.add_argument("set", choices=("fast", "full"), help="the declared set to run")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="the source to run the set against")
    parser.add_argument("--config", type=Path, default=None, help="an alternative gate-sets declaration")
    args = parser.parse_args(arguments)
    source = args.root.resolve()
    try:
        partition = load_gate_sets(args.config) if args.config is not None else published_sets()
        run = run_set(args.set, source, published_executors(), sets=partition)
    except CannotRun as exc:
        print(f"gate-set: CANNOT RUN: {exc}", file=sys.stderr)
        return 2
    for verdict in run.verdicts:
        print(f"{verdict.gate}: exit {verdict.status} in {verdict.seconds}s; evidence {verdict.evidence_digest}")
    print(f"gate-set {args.set}: exit {run.status} against {run.source}")
    return run.status


if __name__ == "__main__":
    raise SystemExit(main())
