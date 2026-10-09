"""Per-requirement delivery-state records: SPECIFIED, LANDED, VERIFIED or RETIRED."""

from __future__ import annotations

from collections import defaultdict

from pipelines_hooks.specs.ids import TOKEN_RE
from pipelines_hooks.specs.requirements_doc import Row

#: How many landing commits / bound tests a record shows at most.
MAX_EVIDENCE_SHOWN = 5


def mentioned_tokens(commits: dict[str, str]) -> dict[str, set[str]]:
    """requirement ID -> commit SHAs whose landing message names it exactly."""
    mentioned: dict[str, set[str]] = defaultdict(set)
    for sha, message in commits.items():
        for token in TOKEN_RE.findall(message):
            mentioned[token].add(sha)
    return mentioned


def _delivery_state(row: Row, landed: list[str], tests: list[str]) -> str:
    if row.retired_reason is not None:
        return "RETIRED"
    if landed and tests:
        return "VERIFIED"
    if landed:
        return "LANDED"
    return "SPECIFIED"


def build_record(row: Row, landed: list[str], tests: list[str]) -> dict[str, object]:
    """The published record for one requirement row."""
    record: dict[str, object] = {
        "id": row.id,
        "title": row.title,
        "delivery_state": _delivery_state(row, landed, tests),
        "landed_in": [sha[:12] for sha in landed[:MAX_EVIDENCE_SHOWN]],
        "verified_by": tests[:MAX_EVIDENCE_SHOWN],
    }
    if row.retired_reason is not None:
        record["retired_reason"] = row.retired_reason
    return record
