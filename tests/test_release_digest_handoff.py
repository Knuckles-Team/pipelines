"""Digest handoff and consumer-manifest verification (FR-4: P-4, N-6)."""

from __future__ import annotations

from release_fixtures import candidates_abc

from scripts.release.digest_handoff import verify_consumer_manifest
from scripts.release.models import ReleaseRun, StageOutcome


def _run() -> ReleaseRun:
    candidates = candidates_abc()
    outcomes = tuple(
        StageOutcome(c.component_id, c.source_commit, c.artifact_digest, f"https://ci/{c.component_id}", "published")
        for c in candidates.candidates
    )
    return ReleaseRun(set_digest=candidates.digest(), outcomes=outcomes)


def test_a_digest_pinned_manifest_exactly_matching_the_qualified_mapping_is_ready() -> None:
    run = _run()
    declared = {component_id: digest for component_id, digest in run.digest_mapping().items()}
    assert verify_consumer_manifest(run, declared) == []


def test_a_floating_workload_reference_names_the_workload_and_blocks_readiness() -> None:
    run = _run()
    declared = dict(run.digest_mapping())
    declared["B"] = "latest"
    problems = verify_consumer_manifest(run, declared)
    assert len(problems) == 1
    assert "B" in problems[0]
    assert "floating tag" in problems[0]


def test_a_wrong_pinned_digest_names_the_workload_and_blocks_readiness() -> None:
    run = _run()
    declared = dict(run.digest_mapping())
    declared["C"] = "sha256:" + "0" * 64
    problems = verify_consumer_manifest(run, declared)
    assert len(problems) == 1
    assert "C" in problems[0]
    assert "digest mismatch" in problems[0]


def test_a_component_absent_from_the_qualified_release_is_named() -> None:
    run = _run()
    problems = verify_consumer_manifest(run, {"not-a-component": "sha256:" + "1" * 64})
    assert "not part of the qualified release" in problems[0]
