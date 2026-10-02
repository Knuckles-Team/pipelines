"""Deterministic order and exact-commit qualification (FR-2, FR-3: P-2, N-3)."""

from __future__ import annotations

from release_fixtures import candidates_abc, checks

from scripts.release.models import CheckResult
from scripts.release.ordering import topological_order
from scripts.release.qualification import RecordedChecksClient, qualify


def test_topological_order_is_a_then_b_then_c() -> None:
    assert topological_order(candidates_abc()) == ["A", "B", "C"]


def test_required_exact_commit_checks_passing_mark_every_candidate_eligible() -> None:
    candidates = candidates_abc()
    order = topological_order(candidates)
    result = qualify(candidates, order, checks("checks_all_pass.json"))
    assert result.eligible == frozenset({"A", "B", "C"})
    assert result.blocked == {}


def test_a_failing_check_blocks_that_candidate_and_its_descendants() -> None:
    candidates = candidates_abc()
    order = topological_order(candidates)
    result = qualify(candidates, order, checks("checks_b_fails.json"))
    assert result.eligible == frozenset({"A"})
    assert "failing" in result.blocked["B"]
    assert "blocked by predecessor B" in result.blocked["C"]


def test_a_missing_check_blocks_the_candidate() -> None:
    candidates = candidates_abc()
    order = topological_order(candidates)
    result = qualify(candidates, order, RecordedChecksClient({}))
    assert result.eligible == frozenset()
    assert all("missing checks" in reason for reason in result.blocked.values())


def test_a_check_recorded_against_a_different_commit_blocks_the_candidate() -> None:
    candidates = candidates_abc()
    order = topological_order(candidates)
    wrong_commit = "9" * 40
    client = RecordedChecksClient(
        {
            ("Knuckles-Team/component-a", "a" * 40): (
                CheckResult(name="ci/pytest", commit=wrong_commit, outcome="passed"),
            ),
        }
    )
    result = qualify(candidates, order, client)
    assert "different commit" in result.blocked["A"]
