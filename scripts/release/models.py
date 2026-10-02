"""Data model for the dependency-ordered digest release (PIPE-RELEASE-R001).

A :class:`Candidate` is one component's entry in a versioned public candidate
manifest: its repository, the exact source commit the artifact was built
from, the immutable image/profile digests, its predecessor component IDs, the
hosted checks it must pass, and the consumer manifest references that must be
updated to the qualified digest once published. ``tag`` is carried only for
display; nothing here treats it as release authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BuildReceipt:
    """The build/check receipt a candidate must carry for its own digest."""

    source_commit: str
    artifact_digest: str
    run_url: str = ""


@dataclass(frozen=True)
class Candidate:
    """One component of a candidate manifest (FR-1)."""

    component_id: str
    repository: str
    source_commit: str
    artifact_digest: str
    profile_digest: str
    compatibility_range: str
    predecessors: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()
    build_receipt: BuildReceipt | None = None
    tag: str = ""


@dataclass(frozen=True)
class CandidateSet:
    """A full candidate manifest: every component considered for one release."""

    candidates: tuple[Candidate, ...] = field(default_factory=tuple)

    def by_id(self) -> dict[str, Candidate]:
        return {candidate.component_id: candidate for candidate in self.candidates}

    def digest(self) -> str:
        """A stable digest of this candidate set, used to derive idempotency keys."""
        canonical = [
            {
                "component_id": c.component_id,
                "source_commit": c.source_commit,
                "artifact_digest": c.artifact_digest,
            }
            for c in sorted(self.candidates, key=lambda c: c.component_id)
        ]
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CheckResult:
    """One hosted check's recorded outcome at an exact commit."""

    name: str
    commit: str
    outcome: str  # "passed" | "failed" | "skipped"


@dataclass(frozen=True)
class QualificationResult:
    """Which candidates are eligible to publish, and why the rest are blocked (FR-2)."""

    eligible: frozenset[str]
    blocked: dict[str, str]


@dataclass(frozen=True)
class StageOutcome:
    """One stage's publication record (FR-3): commit, run, digest, and outcome."""

    component_id: str
    commit: str
    artifact_digest: str
    workflow_run_url: str
    status: str  # "published" | "blocked" | "skipped"
    reason: str = ""


@dataclass(frozen=True)
class ReleaseRun:
    """The ordered outcome of one release attempt over a candidate set."""

    set_digest: str
    outcomes: tuple[StageOutcome, ...] = ()

    def digest_mapping(self) -> dict[str, str]:
        """Component ID -> qualified artifact digest, for published stages only (FR-4)."""
        return {o.component_id: o.artifact_digest for o in self.outcomes if o.status == "published"}
