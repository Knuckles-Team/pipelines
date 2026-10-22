"""The post-land failure policy: auto-revert by default, fix-forward past a threshold.

A failed post-land gate produces a recorded decision. The failure itself
decides it: the gate runner classifies each failure as ``product`` (the
changeset's own result) or ``infrastructure`` (the gate never produced a
result, for example a lost runner). Unclassified failures are ``product``.

A product failure auto-reverts by default. Fix-forward applies only when
the owner opens a fix-forward task within the window of the failed
verdict. A passing re-run never changes a product failure's decision:
the zero-flake policy never gates on a re-run pass.

An infrastructure failure may be re-run once. A passing re-run records
``infrastructure-rerun``: the re-run's verdict stands and nothing reverts.
A failing or unavailable re-run falls back to the product rules.

The decision record carries the gate ID, the changeset ID, the verdict,
the failure class, the threshold that fired and the evidence digest, and
it is replayable: replaying the record's inputs yields the same decision.
Pipelines publishes the policy; the engine stores the record beside the
changeset.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pipelines_hooks.core.errors import CannotRun

#: The starting default; a measured latency on this platform replaces it.
DEFAULT_WINDOW_SECONDS = 300.0

SCHEMA_VERSION = 2

#: Threshold names the decision record carries.
THRESHOLD_DEFAULT = "default"
THRESHOLD_TASK_WINDOW = "fix-forward-task-window"
THRESHOLD_INFRASTRUCTURE_RERUN = "infrastructure-rerun-pass"

#: Failure classes the gate runner assigns to a failed verdict.
FAILURE_PRODUCT = "product"
FAILURE_INFRASTRUCTURE = "infrastructure"
FAILURE_CLASSES = frozenset({FAILURE_PRODUCT, FAILURE_INFRASTRUCTURE})

DECISIONS = frozenset({"auto-revert", "fix-forward", "infrastructure-rerun"})
THRESHOLDS = frozenset({THRESHOLD_DEFAULT, THRESHOLD_TASK_WINDOW, THRESHOLD_INFRASTRUCTURE_RERUN})
SECOND_RUN_STATUSES = frozenset({"pass", "fail", "unavailable"})


@dataclass(frozen=True)
class FailedVerdict:
    """The failed post-land gate verdict, as recorded against the changeset."""

    gate_id: str
    changeset_id: str
    verdict: str
    verdict_at: datetime
    evidence_digest: str
    #: ``product`` unless the runner proved the gate produced no result.
    failure_class: str = FAILURE_PRODUCT


@dataclass(frozen=True)
class FixForwardTask:
    """One fix-forward task opened in reaction to the failed verdict."""

    opened_at: datetime


@dataclass(frozen=True)
class SecondRun:
    """The failed gate's immediate re-run, when one happened.

    Only an infrastructure failure's re-run can change the decision.
    """

    status: str
    ran_at: datetime


@dataclass(frozen=True)
class DecisionRecord:
    """The recorded decision, complete enough to replay it."""

    gate_id: str
    changeset_id: str
    verdict: str
    verdict_at: datetime
    evidence_digest: str
    failure_class: str
    task_opened_at: datetime | None
    second_run_status: str | None
    second_run_at: datetime | None
    window_seconds: float
    decision: str
    threshold: str


def _aware(moment: datetime, label: str) -> None:
    if moment.tzinfo is None:
        raise CannotRun(f"landing policy: {label} must be timezone-aware")


def _task_opens_window(failed: FailedVerdict, task: FixForwardTask, window_seconds: float) -> bool:
    """True when the task opens inside the window: after the verdict, before it closes.

    The window is half-open at the boundary: a task opened exactly
    ``window_seconds`` after the verdict, or before it, does not open it.
    """
    delta = task.opened_at - failed.verdict_at
    return timedelta(0) <= delta < timedelta(seconds=window_seconds)


def decide(
    failed: FailedVerdict,
    task: FixForwardTask | None = None,
    second_run: SecondRun | None = None,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
) -> DecisionRecord:
    """The recorded decision for one failed post-land verdict.

    Auto-revert is the default. An infrastructure failure whose re-run
    passes records ``infrastructure-rerun``. Otherwise fix-forward fires
    only when the owner opens a fix-forward task inside the window. A
    product failure's re-run result never changes the decision.
    """
    if failed.failure_class not in FAILURE_CLASSES:
        raise CannotRun(f"landing policy: unknown failure class {failed.failure_class!r}")
    _aware(failed.verdict_at, "verdict_at")
    if task is not None:
        _aware(task.opened_at, "task opened_at")
    if second_run is not None:
        if second_run.status not in SECOND_RUN_STATUSES:
            raise CannotRun(f"landing policy: unknown second-run status {second_run.status!r}")
        _aware(second_run.ran_at, "second_run ran_at")
    decision, threshold = "auto-revert", THRESHOLD_DEFAULT
    infrastructure_pass = (
        failed.failure_class == FAILURE_INFRASTRUCTURE and second_run is not None and second_run.status == "pass"
    )
    if infrastructure_pass:
        decision, threshold = "infrastructure-rerun", THRESHOLD_INFRASTRUCTURE_RERUN
    elif task is not None and _task_opens_window(failed, task, window_seconds):
        decision, threshold = "fix-forward", THRESHOLD_TASK_WINDOW
    return DecisionRecord(
        gate_id=failed.gate_id,
        changeset_id=failed.changeset_id,
        verdict=failed.verdict,
        verdict_at=failed.verdict_at,
        evidence_digest=failed.evidence_digest,
        failure_class=failed.failure_class,
        task_opened_at=task.opened_at if task is not None else None,
        second_run_status=second_run.status if second_run is not None else None,
        second_run_at=second_run.ran_at if second_run is not None else None,
        window_seconds=window_seconds,
        decision=decision,
        threshold=threshold,
    )


def replay(record: DecisionRecord) -> DecisionRecord:
    """Re-derive the decision from the record's own inputs.

    The property of the record: ``replay(record) == record``. A record
    whose decision was altered after the fact replays to a different
    decision, which is how a tampered record is detected.
    """
    failed = FailedVerdict(
        record.gate_id,
        record.changeset_id,
        record.verdict,
        record.verdict_at,
        record.evidence_digest,
        record.failure_class,
    )
    task = FixForwardTask(record.task_opened_at) if record.task_opened_at is not None else None
    second_run = (
        SecondRun(record.second_run_status, record.second_run_at)
        if record.second_run_status is not None and record.second_run_at is not None
        else None
    )
    return decide(failed, task, second_run, window_seconds=record.window_seconds)


def _fields(record: DecisionRecord) -> dict[str, object]:
    return {
        "schema": SCHEMA_VERSION,
        "gate_id": record.gate_id,
        "changeset_id": record.changeset_id,
        "verdict": record.verdict,
        "verdict_at": record.verdict_at,
        "evidence_digest": record.evidence_digest,
        "failure_class": record.failure_class,
        "task_opened_at": record.task_opened_at,
        "second_run_status": record.second_run_status,
        "second_run_at": record.second_run_at,
        "window_seconds": record.window_seconds,
        "decision": record.decision,
        "threshold": record.threshold,
    }


def to_dict(record: DecisionRecord) -> dict[str, object]:
    """The record as the engine stores it beside the changeset: stable keys, ISO times."""
    raw = _fields(record)
    return {key: (value.isoformat() if isinstance(value, datetime) else value) for key, value in raw.items()}


def _moment(value: object, key: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CannotRun(f"landing policy: {key} must be an ISO 8601 string or null")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CannotRun(f"landing policy: {key} is not an ISO 8601 time: {value!r}") from exc
    if moment.tzinfo is None:
        raise CannotRun(f"landing policy: {key} must be timezone-aware")
    return moment


def _required_moment(value: object, key: str) -> datetime:
    moment = _moment(value, key)
    if moment is None:
        raise CannotRun(f"landing policy: {key} must be present")
    return moment


def from_dict(payload: Mapping[str, object]) -> DecisionRecord:
    """One stored record, validated strictly; a deviation is a configuration error."""
    expected = set(
        _fields(DecisionRecord("", "", "", datetime.now(timezone.utc), "", "", None, None, None, 0.0, "", ""))
    )
    if set(payload) != expected:
        raise CannotRun(f"landing policy: record keys must be exactly {', '.join(sorted(expected))}")
    if payload["schema"] != SCHEMA_VERSION:
        raise CannotRun(f"landing policy: unsupported schema {payload['schema']!r}")

    def text(key: str) -> str:
        value = payload[key]
        if not isinstance(value, str) or not value:
            raise CannotRun(f"landing policy: {key} must be a non-empty string")
        return value

    gate_id, changeset_id, verdict, evidence_digest = (
        text(key) for key in ("gate_id", "changeset_id", "verdict", "evidence_digest")
    )
    window = payload["window_seconds"]
    if not isinstance(window, (int, float)) or isinstance(window, bool) or window <= 0:
        raise CannotRun("landing policy: window_seconds must be a positive number")
    decision = payload["decision"]
    if decision not in DECISIONS:
        raise CannotRun(f"landing policy: unknown decision {decision!r}")
    threshold = payload["threshold"]
    if threshold not in THRESHOLDS:
        raise CannotRun(f"landing policy: unknown threshold {threshold!r}")
    failure_class = payload["failure_class"]
    if failure_class not in FAILURE_CLASSES:
        raise CannotRun(f"landing policy: unknown failure class {failure_class!r}")
    second_run_status = payload["second_run_status"]
    if second_run_status is not None and second_run_status not in SECOND_RUN_STATUSES:
        raise CannotRun(f"landing policy: unknown second-run status {second_run_status!r}")
    return DecisionRecord(
        gate_id=gate_id,
        changeset_id=changeset_id,
        verdict=verdict,
        verdict_at=_required_moment(payload["verdict_at"], "verdict_at"),
        evidence_digest=evidence_digest,
        failure_class=str(failure_class),
        task_opened_at=_moment(payload["task_opened_at"], "task_opened_at"),
        second_run_status=second_run_status,
        second_run_at=_moment(payload["second_run_at"], "second_run_at"),
        window_seconds=float(window),
        decision=decision,
        threshold=threshold,
    )
