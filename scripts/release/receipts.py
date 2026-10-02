"""Idempotent stage receipts (FR-3).

The idempotency key binds a stage to the exact candidate-set digest, the
candidate's commit, and its artifact digest. Retrying the same candidate
resumes from its recorded receipt instead of republishing; a changed commit
or digest derives a different key and starts a fresh stage rather than
resuming a receipt that no longer describes the same release.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipelines_hooks.core.bounded_json import read_bounded_json

from .models import Candidate, StageOutcome

_MAX_RECEIPT_FILE_BYTES = 1_000_000


def stage_key(set_digest: str, candidate: Candidate) -> str:
    """The idempotency key for one candidate's stage within one candidate set."""
    payload = f"{set_digest}:{candidate.component_id}:{candidate.source_commit}:{candidate.artifact_digest}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FileReceiptStore:
    """A public, inspectable JSON receipt file: one row per idempotency key."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._rows: dict[str, dict[str, str]] = self._load()

    def _load(self) -> dict[str, dict[str, str]]:
        if not self._path.is_file():
            return {}
        payload = read_bounded_json(self._path, _MAX_RECEIPT_FILE_BYTES, what="release receipt file", error=ValueError)
        return dict(payload) if isinstance(payload, dict) else {}

    def load(self, key: str) -> StageOutcome | None:
        row = self._rows.get(key)
        return None if row is None else StageOutcome(**row)

    def save(self, key: str, outcome: StageOutcome) -> None:
        self._rows[key] = outcome.__dict__
        self._path.write_text(json.dumps(self._rows, sort_keys=True, indent=2), encoding="utf-8")
