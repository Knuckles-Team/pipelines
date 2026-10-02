"""Candidate manifest validation (PIPE-RELEASE-R001, FR-1: P-1, N-1, N-2)."""

from __future__ import annotations

import pytest
from release_fixtures import raw_candidates_abc

from scripts.release.candidate import candidate_set_errors, parse_candidate_set
from scripts.release.errors import CandidateSetError


def test_a_valid_a_b_c_manifest_validates_source_and_digest_fields() -> None:
    candidates = parse_candidate_set(raw_candidates_abc())
    assert [c.component_id for c in candidates.candidates] == ["A", "B", "C"]
    assert candidates.by_id()["B"].predecessors == ("A",)


def test_duplicate_component_id_fails_before_publication() -> None:
    raw = raw_candidates_abc()
    raw["candidates"].append(dict(raw["candidates"][0]))
    errors = candidate_set_errors(raw["candidates"])
    assert any("duplicate component id" in error for error in errors)


def test_missing_dependency_fails_before_publication() -> None:
    raw = raw_candidates_abc()
    raw["candidates"][1]["predecessors"] = ["does-not-exist"]
    errors = candidate_set_errors(raw["candidates"])
    assert any("unknown predecessor" in error for error in errors)


def test_self_edge_fails_before_publication() -> None:
    raw = raw_candidates_abc()
    raw["candidates"][0]["predecessors"] = ["A"]
    errors = candidate_set_errors(raw["candidates"])
    assert any("self-referential predecessor" in error for error in errors)


def test_a_cycle_fails_before_publication() -> None:
    raw = raw_candidates_abc()
    raw["candidates"][0]["predecessors"] = ["C"]
    errors = candidate_set_errors(raw["candidates"])
    assert any("dependency cycle" in error for error in errors)


def test_a_floating_tag_without_a_pinned_digest_fails_closed() -> None:
    raw = raw_candidates_abc()
    raw["candidates"][0]["artifact_digest"] = ""
    raw["candidates"][0]["tag"] = "latest"
    errors = candidate_set_errors(raw["candidates"])
    assert any("floating tag" in error for error in errors)


def test_a_malformed_digest_fails_closed() -> None:
    raw = raw_candidates_abc()
    raw["candidates"][0]["artifact_digest"] = "sha256:not-hex"
    errors = candidate_set_errors(raw["candidates"])
    assert any("malformed or missing artifact digest" in error for error in errors)


def test_a_provenance_mismatch_between_receipt_and_candidate_fails_closed() -> None:
    raw = raw_candidates_abc()
    raw["candidates"][0]["build_receipt"]["artifact_digest"] = "sha256:" + "f" * 64
    errors = candidate_set_errors(raw["candidates"])
    assert any("build receipt digest does not match" in error for error in errors)


def test_parse_raises_candidate_set_error_on_any_problem() -> None:
    raw = raw_candidates_abc()
    raw["candidates"][0]["predecessors"] = ["A"]
    with pytest.raises(CandidateSetError):
        parse_candidate_set(raw)
