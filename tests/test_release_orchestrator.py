"""Ordered stage publication and idempotent retries (FR-3: P-3, N-4, N-5)."""

from __future__ import annotations

from pathlib import Path

from release_fixtures import candidates_abc, checks, raw_candidates_abc, success_plan

from scripts.release.candidate import parse_candidate_set
from scripts.release.models import StageOutcome
from scripts.release.ordering import topological_order
from scripts.release.orchestrator import RecordedPublisher, orchestrate
from scripts.release.receipts import FileReceiptStore


def test_a_then_b_then_c_publish_in_order_recording_hosted_ci(tmp_path: Path) -> None:
    candidates = candidates_abc()
    order = topological_order(candidates)
    run = orchestrate(
        candidates,
        order,
        checks=checks("checks_all_pass.json"),
        publisher=RecordedPublisher(success_plan(candidates)),
        receipts=FileReceiptStore(tmp_path / "receipts.json"),
    )
    assert [o.component_id for o in run.outcomes] == ["A", "B", "C"]
    assert all(o.status == "published" for o in run.outcomes)
    assert all(o.workflow_run_url for o in run.outcomes)


def test_a_failed_predecessor_check_prevents_the_next_push(tmp_path: Path) -> None:
    candidates = candidates_abc()
    order = topological_order(candidates)
    run = orchestrate(
        candidates,
        order,
        checks=checks("checks_b_fails.json"),
        publisher=RecordedPublisher(success_plan(candidates)),
        receipts=FileReceiptStore(tmp_path / "receipts.json"),
    )
    by_id = {o.component_id: o for o in run.outcomes}
    assert by_id["A"].status == "published"
    assert by_id["B"].status == "blocked"
    assert by_id["C"].status == "skipped"


def test_a_same_digest_retry_resumes_without_republishing(tmp_path: Path) -> None:
    candidates = candidates_abc()
    order = topological_order(candidates)
    receipts_path = tmp_path / "receipts.json"
    publish_calls: list[str] = []

    class CountingPublisher:
        def __init__(self, plan: dict[str, StageOutcome]) -> None:
            self._plan = plan

        def publish(self, candidate) -> StageOutcome:
            publish_calls.append(candidate.component_id)
            return self._plan[candidate.component_id]

    publisher = CountingPublisher(success_plan(candidates))
    checks_client = checks("checks_all_pass.json")
    first = orchestrate(candidates, order, checks=checks_client, publisher=publisher, receipts=FileReceiptStore(receipts_path))
    second = orchestrate(candidates, order, checks=checks_client, publisher=publisher, receipts=FileReceiptStore(receipts_path))
    assert publish_calls == ["A", "B", "C"]  # not six: the retry resumed every stage from its receipt
    assert first == second


def test_a_changed_artifact_digest_cannot_resume_the_old_receipt(tmp_path: Path) -> None:
    candidates = candidates_abc()
    order = topological_order(candidates)
    receipts_path = tmp_path / "receipts.json"
    checks_client = checks("checks_all_pass.json")
    orchestrate(
        candidates,
        order,
        checks=checks_client,
        publisher=RecordedPublisher(success_plan(candidates)),
        receipts=FileReceiptStore(receipts_path),
    )

    raw = raw_candidates_abc()
    new_digest = "sha256:" + "9" * 64
    raw["candidates"][0]["artifact_digest"] = new_digest
    raw["candidates"][0]["build_receipt"]["artifact_digest"] = new_digest
    changed_candidates = parse_candidate_set(raw)
    second = orchestrate(
        changed_candidates,
        order,
        checks=checks_client,
        publisher=RecordedPublisher(success_plan(changed_candidates)),
        receipts=FileReceiptStore(receipts_path),
    )
    assert second.outcomes[0].artifact_digest == new_digest
    assert second.set_digest != candidates.digest()
