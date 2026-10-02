"""Ordered stage publication (FR-3).

Publish one dependency stage at a time, in the deterministic topological
order, and stop before any downstream publication once a stage is blocked or
fails. Each attempted stage is recorded through the idempotent receipt store,
so retrying an interrupted release resumes rather than republishing a
completed digest.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import Candidate, CandidateSet, ReleaseRun, StageOutcome
from .qualification import ChecksClient, qualify
from .receipts import FileReceiptStore, stage_key


class Publisher(Protocol):
    """Publishes one qualified candidate and reports its hosted outcome."""

    def publish(self, candidate: Candidate) -> StageOutcome:
        ...


class RecordedPublisher:
    """Replays a pre-recorded publish plan -- the portable/dry-run adapter (FR-5).

    A live adapter that pushes a revision and polls hosted CI for real
    belongs to the production release runner; it is not implemented here
    (see the lane report: it needs network-reachable GitHub/registry
    credentials this host does not have).
    """

    def __init__(self, plan: dict[str, StageOutcome]) -> None:
        self._plan = plan

    def publish(self, candidate: Candidate) -> StageOutcome:
        return self._plan.get(
            candidate.component_id,
            StageOutcome(candidate.component_id, candidate.source_commit, candidate.artifact_digest, "", "blocked", "no recorded publish plan"),
        )


def orchestrate(
    candidates: CandidateSet,
    order: Sequence[str],
    *,
    checks: ChecksClient,
    publisher: Publisher,
    receipts: FileReceiptStore,
) -> ReleaseRun:
    """Run one ordered release attempt; stop before publishing past the first failure."""
    by_id = candidates.by_id()
    qualification = qualify(candidates, order, checks)
    set_digest = candidates.digest()
    outcomes: list[StageOutcome] = []
    stopped = False
    for component_id in order:
        outcome, stopped = _stage(
            by_id[component_id],
            qualification.blocked,
            publisher=publisher,
            receipts=receipts,
            set_digest=set_digest,
            stopped=stopped,
        )
        outcomes.append(outcome)
    return ReleaseRun(set_digest=set_digest, outcomes=tuple(outcomes))


def _stage(
    candidate: Candidate,
    blocked: dict[str, str],
    *,
    publisher: Publisher,
    receipts: FileReceiptStore,
    set_digest: str,
    stopped: bool,
) -> tuple[StageOutcome, bool]:
    if stopped:
        return _skip(candidate, "an upstream stage did not publish"), True
    if candidate.component_id in blocked:
        return _skip(candidate, blocked[candidate.component_id], status="blocked"), True
    key = stage_key(set_digest, candidate)
    existing = receipts.load(key)
    if existing is not None:
        return existing, existing.status != "published"
    outcome = publisher.publish(candidate)
    receipts.save(key, outcome)
    return outcome, outcome.status != "published"


def _skip(candidate: Candidate, reason: str, *, status: str = "skipped") -> StageOutcome:
    return StageOutcome(candidate.component_id, candidate.source_commit, candidate.artifact_digest, "", status, reason)
