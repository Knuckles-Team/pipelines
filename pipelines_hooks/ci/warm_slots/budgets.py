"""Warm slot timing budgets (PIPE-GATES-R075).

``up`` records the cold prime of each slot and the pull request job records
its wall time and its warm one-file check, all in one JSON timings file.
A recorded measurement over its limit is a finding that names the
measurement and the limit. A cold prime on a slot with fewer than eight
jobs is judged against the limit scaled by ``8 / jobs``; the limit is the
eight-job figure.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

REFERENCE_JOBS = 8
WARM_CHECK = "warm_one_file_check"
COLD_PRIME = "cold_prime"
PR_WALL = "pr_wall_time"


@dataclass(frozen=True)
class Budgets:
    """The three limits, in seconds."""

    warm_check_seconds: float = 60.0
    cold_prime_seconds: float = 900.0
    pr_wall_seconds: float = 1200.0


@dataclass(frozen=True)
class Timing:
    """One recorded measurement."""

    measurement: str
    seconds: float
    subject: str = ""
    jobs: int = REFERENCE_JOBS


def record_timing(path: Path, timing: Timing) -> None:
    """Append one measurement to the timings file."""
    entries = [
        *_raw(path),
        {"measurement": timing.measurement, "seconds": timing.seconds, "subject": timing.subject, "jobs": timing.jobs},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _raw(path: Path) -> list[Mapping[str, object]]:
    if not path.is_file():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRun(f"warm slots: cannot read the timings file {path.name}: {exc}") from None
    if not isinstance(entries, list):
        raise CannotRun(f"warm slots: the timings file {path.name} must hold a list")
    return entries


def load_timings(path: Path) -> list[Timing]:
    """The recorded measurements; a malformed entry cannot be judged and cannot run."""
    timings = []
    for entry in _raw(path):
        try:
            timings.append(
                Timing(
                    str(entry["measurement"]),
                    float(str(entry["seconds"])),
                    str(entry.get("subject", "")),
                    int(str(entry.get("jobs", REFERENCE_JOBS))),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CannotRun(f"warm slots: a timings entry is malformed: {exc}") from None
    return timings


def check_budgets(timings: Sequence[Timing], budgets: Budgets) -> list[str]:
    """One finding per measurement over its limit, naming the measurement and the limit."""
    findings = []
    for timing in timings:
        limit, label = {
            WARM_CHECK: (budgets.warm_check_seconds, "a warm one-file-change check"),
            COLD_PRIME: (budgets.cold_prime_seconds, "a cold prime"),
            PR_WALL: (budgets.pr_wall_seconds, "pull request CI wall time"),
        }.get(timing.measurement, (None, ""))
        if limit is None:
            continue
        if timing.measurement == COLD_PRIME and 0 < timing.jobs < REFERENCE_JOBS:
            limit = limit * REFERENCE_JOBS / timing.jobs
        if timing.seconds > limit:
            subject = f" ({timing.subject})" if timing.subject else ""
            findings.append(
                f"{timing.measurement}{subject}: {label} took {timing.seconds:g}s, over the {limit:g}s limit"
            )
    return findings
