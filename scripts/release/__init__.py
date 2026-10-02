"""Dependency-ordered digest release orchestration (PIPE-RELEASE-R001, PIPE-RELEASE-R003).

See ``specs/ordered-digest-release/`` for the owning specification. This
package is portable: every module here runs against local fixtures, with no
network call and no hosted credential, per FR-5 (``plan.md#portable-execution``).
"""

from __future__ import annotations

from .candidate import candidate_set_errors, parse_candidate_set
from .digest_handoff import verify_consumer_manifest
from .errors import CandidateSetError, ReleaseError, ReproducibilityError
from .models import (
    BuildReceipt,
    Candidate,
    CandidateSet,
    CheckResult,
    QualificationResult,
    ReleaseRun,
    StageOutcome,
)
from .ordering import topological_order
from .orchestrator import RecordedPublisher, orchestrate
from .qualification import RecordedChecksClient, qualify
from .receipts import FileReceiptStore, stage_key
from .reproducibility import ReproducibilityResult, build_wheel_twice, compare_wheels

__all__ = [
    "BuildReceipt",
    "Candidate",
    "CandidateSet",
    "CandidateSetError",
    "CheckResult",
    "FileReceiptStore",
    "QualificationResult",
    "RecordedChecksClient",
    "RecordedPublisher",
    "ReleaseError",
    "ReleaseRun",
    "ReproducibilityError",
    "ReproducibilityResult",
    "StageOutcome",
    "build_wheel_twice",
    "candidate_set_errors",
    "compare_wheels",
    "orchestrate",
    "parse_candidate_set",
    "qualify",
    "stage_key",
    "topological_order",
    "verify_consumer_manifest",
]
