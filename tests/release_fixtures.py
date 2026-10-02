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


_REPRODUCIBLE_PYPROJECT = """\
[build-system]
requires = ["setuptools>=80"]
build-backend = "setuptools.build_meta"

[project]
name = "reprofixture"
version = "0.0.1"
description = "A trivial pure-Python fixture package for the wheel reproducibility test."
"""

_REPRODUCIBLE_INIT = '''\
"""Trivial fixture package used only to prove wheel reproducibility (PIPE-RELEASE-R003)."""

VALUE = 1
'''


def write_reproducible_fixture(destination: Path) -> Path:
    """A minimal, buildable pure-Python package written fresh at ``destination``.

    Generated at test time rather than checked in as a tracked ``pyproject.toml``:
    a second tracked project-boundary file under ``tests/`` confuses tooling that
    walks the tree looking for one (observed with the KISS census scanner).
    """
    package_dir = destination / "src" / "reprofixture"
    package_dir.mkdir(parents=True, exist_ok=True)
    (destination / "pyproject.toml").write_text(_REPRODUCIBLE_PYPROJECT, encoding="utf-8")
    (package_dir / "__init__.py").write_text(_REPRODUCIBLE_INIT, encoding="utf-8")
    return destination
