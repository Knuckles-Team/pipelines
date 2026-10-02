"""Exact-commit qualification gating (FR-2).

A candidate is eligible only when every one of its required checks is
recorded as passed at its exact source commit. A missing, skipped, failing,
or wrong-commit check blocks that candidate and every descendant that
depends on it (directly or transitively) -- the release reports the eligible
subset instead of claiming a full release.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import Candidate, CandidateSet, CheckResult, QualificationResult


class ChecksClient(Protocol):
    """Looks up recorded hosted-check results for one repository and commit."""

    def check_results(self, repository: str, commit: str) -> tuple[CheckResult, ...]:
        ...


class RecordedChecksClient:
    """Reads check results recorded ahead of time -- the portable/dry-run adapter (FR-5).

    A live adapter that polls the hosted checks API for real belongs to the
    production release runner; it is not implemented here (see the lane
    report: it needs a network-reachable GitHub token this host does not
    have). This client lets ordering, qualification, and refusal logic run
    and be tested against those same recorded results, with no network call.
    """

    def __init__(self, recorded: dict[tuple[str, str], tuple[CheckResult, ...]]) -> None:
        self._recorded = recorded

    def check_results(self, repository: str, commit: str) -> tuple[CheckResult, ...]:
        return self._recorded.get((repository, commit), ())


def qualify(candidates: CandidateSet, order: Sequence[str], checks: ChecksClient) -> QualificationResult:
    """The eligible subset and the blocked reasons, walked in dependency order."""
    by_id = candidates.by_id()
    eligible: set[str] = set()
    blocked: dict[str, str] = {}
    for component_id in order:
        candidate = by_id[component_id]
        reason = _blocked_by_predecessor(candidate, blocked) or _ineligibility_reason(candidate, checks)
        if reason:
            blocked[component_id] = reason
        else:
            eligible.add(component_id)
    return QualificationResult(eligible=frozenset(eligible), blocked=blocked)


def _blocked_by_predecessor(candidate: Candidate, blocked: dict[str, str]) -> str:
    for predecessor in candidate.predecessors:
        if predecessor in blocked:
            return f"blocked by predecessor {predecessor}: {blocked[predecessor]}"
    return ""


def _ineligibility_reason(candidate: Candidate, checks: ChecksClient) -> str:
    results = {result.name: result for result in checks.check_results(candidate.repository, candidate.source_commit)}
    missing = [name for name in candidate.required_checks if name not in results]
    failing = [name for name in candidate.required_checks if name in results and results[name].outcome != "passed"]
    wrong_commit = sorted(
        {name for name, result in results.items() if result.commit != candidate.source_commit}
    )
    bits = []
    if missing:
        bits.append(f"missing checks: {', '.join(missing)}")
    if failing:
        bits.append(f"failing or skipped checks: {', '.join(failing)}")
    if wrong_commit:
        bits.append(f"checks recorded against a different commit: {', '.join(wrong_commit)}")
    return "; ".join(bits)
