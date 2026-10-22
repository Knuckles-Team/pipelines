"""The post-land failure policy (PIPE-GATES-R002): T-002 and T-003.

Auto-revert is the default; fix-forward applies only when the owner opens
a fix-forward task inside the 300 s window of the failed verdict. A
passing re-run never changes a product failure's decision (zero-flake).
Only an infrastructure-classified failure whose re-run passes records an
infrastructure re-run. The decision record carries the gate ID, the
changeset ID, the verdict, the failure class, the threshold that fired
and the evidence digest, and it replays to its own decision.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.landing_policy import (
    DEFAULT_WINDOW_SECONDS,
    FailedVerdict,
    FixForwardTask,
    SecondRun,
    THRESHOLDS,
    decide,
    from_dict,
    replay,
    to_dict,
)

VERDICT_AT = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


def _failed(failure_class: str = "product") -> FailedVerdict:
    return FailedVerdict(
        gate_id="supply-chain",
        changeset_id="cs-42",
        verdict="fail",
        verdict_at=VERDICT_AT,
        evidence_digest="sha256:0f1e2d3c",
        failure_class=failure_class,
    )


def test_no_task_and_a_failing_second_run_auto_reverts() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed(), second_run=SecondRun("fail", VERDICT_AT + timedelta(seconds=60)))
    assert record.decision == "auto-revert"
    assert record.threshold == "default"
    assert record.gate_id == "supply-chain"
    assert record.changeset_id == "cs-42"
    assert record.verdict == "fail"
    assert record.verdict_at == VERDICT_AT
    assert record.evidence_digest == "sha256:0f1e2d3c"
    assert record.failure_class == "product"
    assert record.task_opened_at is None
    assert record.second_run_status == "fail"
    assert record.window_seconds == DEFAULT_WINDOW_SECONDS


def test_a_task_opened_after_the_window_auto_reverts() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed(), task=FixForwardTask(VERDICT_AT + timedelta(seconds=301)))
    assert record.decision == "auto-revert"
    assert record.threshold == "default"


def test_an_unavailable_second_run_auto_reverts_and_is_recorded() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed(), second_run=SecondRun("unavailable", VERDICT_AT + timedelta(seconds=30)))
    assert record.decision == "auto-revert"
    assert record.threshold == "default"
    assert record.second_run_status == "unavailable"
    assert record.second_run_at == VERDICT_AT + timedelta(seconds=30)


def test_a_task_inside_the_window_is_fix_forward() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed(), task=FixForwardTask(VERDICT_AT + timedelta(seconds=299)))
    assert record.decision == "fix-forward"
    assert record.threshold == "fix-forward-task-window"
    assert record.task_opened_at == VERDICT_AT + timedelta(seconds=299)
    assert record.gate_id == "supply-chain"
    assert record.changeset_id == "cs-42"
    assert record.verdict == "fail"
    assert record.evidence_digest == "sha256:0f1e2d3c"


def test_a_product_failure_whose_rerun_passes_still_auto_reverts() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed(), second_run=SecondRun("pass", VERDICT_AT + timedelta(seconds=5)))
    assert record.decision == "auto-revert"
    assert record.threshold == "default"
    assert record.second_run_status == "pass"


def test_no_threshold_accepts_a_rerun_pass_of_a_product_failure() -> None:
    # spec: PIPE-GATES-R002
    assert "second-run-pass" not in THRESHOLDS


def test_an_infrastructure_failure_whose_rerun_passes_is_an_infrastructure_rerun() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed("infrastructure"), second_run=SecondRun("pass", VERDICT_AT + timedelta(seconds=5)))
    assert record.decision == "infrastructure-rerun"
    assert record.threshold == "infrastructure-rerun-pass"
    assert record.failure_class == "infrastructure"


def test_an_infrastructure_failure_whose_rerun_fails_auto_reverts() -> None:
    # spec: PIPE-GATES-R002
    for status in ("fail", "unavailable"):
        record = decide(_failed("infrastructure"), second_run=SecondRun(status, VERDICT_AT + timedelta(seconds=5)))
        assert record.decision == "auto-revert"
        assert record.threshold == "default"


def test_an_infrastructure_failure_without_a_rerun_follows_the_product_rules() -> None:
    # spec: PIPE-GATES-R002
    assert decide(_failed("infrastructure")).decision == "auto-revert"
    record = decide(_failed("infrastructure"), task=FixForwardTask(VERDICT_AT + timedelta(seconds=30)))
    assert record.decision == "fix-forward"
    assert record.threshold == "fix-forward-task-window"


def test_an_unknown_failure_class_is_refused() -> None:
    # spec: PIPE-GATES-R002
    with pytest.raises(CannotRun, match="unknown failure class"):
        decide(_failed("flaky"))


def test_a_task_at_the_window_boundary_auto_reverts() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed(), task=FixForwardTask(VERDICT_AT + timedelta(seconds=300)))
    assert record.decision == "auto-revert"
    assert record.threshold == "default"


def test_a_failing_second_run_again_auto_reverts() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed(), second_run=SecondRun("fail", VERDICT_AT + timedelta(seconds=5)))
    assert record.decision == "auto-revert"
    assert record.threshold == "default"


def test_the_owner_task_decides_a_product_failure_whatever_the_rerun() -> None:
    # spec: PIPE-GATES-R002
    record = decide(
        _failed(),
        task=FixForwardTask(VERDICT_AT + timedelta(seconds=30)),
        second_run=SecondRun("pass", VERDICT_AT + timedelta(seconds=5)),
    )
    assert record.decision == "fix-forward"
    assert record.threshold == "fix-forward-task-window"


def test_a_passing_infrastructure_rerun_outranks_the_owner_task() -> None:
    # spec: PIPE-GATES-R002
    record = decide(
        _failed("infrastructure"),
        task=FixForwardTask(VERDICT_AT + timedelta(seconds=30)),
        second_run=SecondRun("pass", VERDICT_AT + timedelta(seconds=5)),
    )
    assert record.decision == "infrastructure-rerun"


def test_a_task_opened_before_the_verdict_does_not_open_the_window() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed(), task=FixForwardTask(VERDICT_AT - timedelta(seconds=1)))
    assert record.decision == "auto-revert"


def test_every_recorded_decision_replays_to_itself() -> None:
    # spec: PIPE-GATES-R002
    records = [
        decide(_failed()),
        decide(_failed(), task=FixForwardTask(VERDICT_AT + timedelta(seconds=299))),
        decide(_failed(), task=FixForwardTask(VERDICT_AT + timedelta(seconds=301))),
        decide(_failed(), second_run=SecondRun("pass", VERDICT_AT + timedelta(seconds=5))),
        decide(_failed(), second_run=SecondRun("fail", VERDICT_AT + timedelta(seconds=5))),
        decide(_failed(), second_run=SecondRun("unavailable", VERDICT_AT + timedelta(seconds=5))),
        decide(_failed("infrastructure"), second_run=SecondRun("pass", VERDICT_AT + timedelta(seconds=5))),
        decide(_failed("infrastructure"), second_run=SecondRun("fail", VERDICT_AT + timedelta(seconds=5))),
        decide(
            _failed(),
            task=FixForwardTask(VERDICT_AT + timedelta(seconds=30)),
            second_run=SecondRun("pass", VERDICT_AT + timedelta(seconds=5)),
        ),
        decide(_failed(), window_seconds=120.0),
    ]
    assert records
    for record in records:
        assert replay(record) == record


def test_a_tampered_record_does_not_replay_to_its_own_decision() -> None:
    # spec: PIPE-GATES-R002
    reverted = decide(_failed())
    assert reverted.decision == "auto-revert"
    tampered = replace(reverted, decision="fix-forward")
    assert replay(tampered) != tampered
    assert replay(tampered).decision == "auto-revert"
    fixed = decide(_failed(), task=FixForwardTask(VERDICT_AT + timedelta(seconds=30)))
    tampered_fixed = replace(fixed, decision="auto-revert")
    assert replay(tampered_fixed) != tampered_fixed
    rerun = decide(_failed("infrastructure"), second_run=SecondRun("pass", VERDICT_AT + timedelta(seconds=5)))
    relabelled = replace(rerun, failure_class="product")
    assert replay(relabelled).decision == "auto-revert"


def test_the_record_serializes_to_a_stable_stored_form_and_back() -> None:
    # spec: PIPE-GATES-R002
    record = decide(_failed(), task=FixForwardTask(VERDICT_AT + timedelta(seconds=299)))
    stored = to_dict(record)
    assert stored["schema"] == 2
    assert stored["failure_class"] == "product"
    assert stored["verdict_at"] == "2026-10-20T12:00:00+00:00"
    assert from_dict(stored) == record


def test_the_stored_form_refuses_a_foreign_payload() -> None:
    # spec: PIPE-GATES-R002
    stored = to_dict(decide(_failed()))
    with pytest.raises(CannotRun, match="unknown decision"):
        from_dict({**stored, "decision": "revert"})
    with pytest.raises(CannotRun, match="unknown threshold"):
        from_dict({**stored, "threshold": "heroics"})
    with pytest.raises(CannotRun, match="unknown failure class"):
        from_dict({**stored, "failure_class": "flaky"})
    with pytest.raises(CannotRun, match="unknown second-run status"):
        from_dict({**stored, "second_run_status": "magic"})
    with pytest.raises(CannotRun, match="window_seconds"):
        from_dict({**stored, "window_seconds": 0})
    with pytest.raises(CannotRun, match="schema"):
        from_dict({**stored, "schema": 99})
    with pytest.raises(CannotRun, match="unknown threshold"):
        from_dict({**stored, "threshold": "second-run-pass"})
    with pytest.raises(CannotRun, match="timezone-aware"):
        from_dict({**stored, "verdict_at": "2026-10-20T12:00:00"})
    foreign = {key: value for key, value in stored.items() if key != "evidence_digest"}
    foreign["gate"] = "supply-chain"
    with pytest.raises(CannotRun, match="record keys"):
        from_dict(foreign)


def test_a_naive_timestamp_is_rejected() -> None:
    # spec: PIPE-GATES-R002
    naive = FailedVerdict("spec", "cs-1", "fail", datetime(2026, 10, 20, 12, 0, 0), "sha256:aa")
    with pytest.raises(CannotRun, match="timezone-aware"):
        decide(naive)
