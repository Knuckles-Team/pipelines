"""Shared fixtures for the dependency-ordered release tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.release.candidate import parse_candidate_set
from scripts.release.models import CandidateSet, CheckResult, StageOutcome
from scripts.release.qualification import RecordedChecksClient

FIXTURES = Path(__file__).parent / "fixtures" / "release"


def candidates_abc(raw: dict | None = None) -> CandidateSet:
    """The A -> B -> C candidate set, or ``parse_candidate_set(raw)`` of a modified copy."""
    payload = raw if raw is not None else json.loads((FIXTURES / "candidates_abc.json").read_text(encoding="utf-8"))
    return parse_candidate_set(payload)


def raw_candidates_abc() -> dict:
    """A fresh, mutable copy of the A -> B -> C manifest for negative-case edits."""
    return json.loads((FIXTURES / "candidates_abc.json").read_text(encoding="utf-8"))


def checks(name: str) -> RecordedChecksClient:
    """A :class:`RecordedChecksClient` built from one of the ``fixtures/release`` files."""
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    recorded = {
        (row["repository"], row["commit"]): tuple(CheckResult(**item) for item in row["results"])
        for row in raw
    }
    return RecordedChecksClient(recorded)


def success_plan(candidate_set: CandidateSet) -> dict[str, StageOutcome]:
    """A publish plan recording every candidate as published at its own digest."""
    return {
        c.component_id: StageOutcome(c.component_id, c.source_commit, c.artifact_digest, f"https://ci/{c.component_id}", "published")
        for c in candidate_set.candidates
    }
