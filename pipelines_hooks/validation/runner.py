"""Single dispatch, shared deadlines, and explicit outcome aggregation."""

from __future__ import annotations

import os
import importlib
import signal
import subprocess
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.settings import process_environment
from pipelines_hooks.validation.policy import GATES, Policy


def _terminate(process: subprocess.Popen, output) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError as exc:
        output.write(f"Process group already exited: {exc}\n".encode())
    process.wait()


def execute(command: list[str], root: Path, log: Path, *, timeout: float) -> dict:
    started = time.monotonic()
    with log.open("xb") as output:
        try:
            process = subprocess.Popen(
                command,
                cwd=root,
                env=process_environment(),
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            output.write(f"Cannot start check: {exc}\n".encode())
            return {"outcome": "unavailable", "exit_code": 2, "seconds": 0.0}
        try:
            code = process.wait(timeout=timeout)
            outcome = {0: "pass", 1: "fail", 2: "unavailable"}.get(code, "unavailable")
        except subprocess.TimeoutExpired:
            code, outcome = 2, "timeout"
        finally:
            # Also reap descendants left behind by an exited worker.
            _terminate(process, output)
    return {
        "outcome": outcome,
        "exit_code": code,
        "seconds": round(time.monotonic() - started, 3),
    }


def exit_code(results: list[dict]) -> int:
    outcomes = {row["outcome"] for row in results if row["required"]}
    if outcomes & {"unavailable", "timeout"}:
        return 2
    return int("fail" in outcomes)


def run(policy: Policy, root: Path, evidence: Path) -> dict:
    started = time.monotonic()
    deadline = started + policy.budget_seconds
    prerequisite = ""
    if os.name != "posix":
        prerequisite = "POSIX process groups are required for bounded execution"
    elif shutil.which("git") is None:
        prerequisite = "Git is unavailable; provision Git explicitly and rerun"
    results = []
    for check in policy.checks:
        row = asdict(check)
        log = evidence / f"{check.id}.log"
        remaining = deadline - time.monotonic()
        if prerequisite or remaining <= 0:
            outcome = "unavailable" if prerequisite else "timeout"
            log.write_text(prerequisite or "Run budget exhausted before dispatch\n")
            result = {"outcome": outcome, "exit_code": 2, "seconds": 0.0}
        else:
            command = [
                sys.executable,
                "-m",
                "pipelines_hooks.validation.runner",
                check.gate,
                "--root",
                str(root),
            ]
            result = execute(
                command, root, log, timeout=min(check.timeout_seconds, remaining)
            )
        results.append({**row, **result, "log": str(log)})
    return {
        "version": 1,
        "state": "completed",
        "exit_code": exit_code(results),
        "seconds": round(time.monotonic() - started, 3),
        "checks": results,
    }


def worker(argv: list[str]) -> int:
    if not argv or argv[0] not in GATES:
        print("Unavailable: unsupported offline validation gate", file=sys.stderr)
        return 2
    from pipelines_hooks.cli import GATES as MODULES

    try:
        module = importlib.import_module(MODULES[argv[0]])
        return int(module.main(argv[1:]))
    except (CannotRun, ImportError, OSError) as exc:
        print(
            f"Unavailable: {exc}; provision prerequisites explicitly, then rerun",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(worker(sys.argv[1:]))
