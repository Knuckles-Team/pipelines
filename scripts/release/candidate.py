"""Parse and strictly validate a candidate manifest (FR-1).

Reject cycles, missing dependencies, duplicate identities, floating tags, and
mismatched source/digest provenance before any publication effect. Validation
collects every problem instead of stopping at the first, so a contributor
sees the whole candidate set's refusal in one run.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

import networkx as nx

from .errors import CandidateSetError
from .models import BuildReceipt, Candidate, CandidateSet

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def parse_candidate_set(raw: Mapping[str, Any]) -> CandidateSet:
    """The validated :class:`CandidateSet`; raises :class:`CandidateSetError` otherwise."""
    entries = raw.get("candidates", [])
    errors = candidate_set_errors(entries)
    if errors:
        raise CandidateSetError("; ".join(errors))
    return CandidateSet(candidates=tuple(_build_candidate(entry) for entry in entries))


def candidate_set_errors(entries: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every validation problem in ``entries``, or an empty list when it is clean."""
    ids = [entry.get("component_id", "") for entry in entries]
    errors: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        errors.extend(_entry_errors(entry, ids, seen))
    errors.extend(_cycle_errors(entries))
    return errors


def _entry_errors(entry: Mapping[str, Any], ids: Sequence[str], seen: set[str]) -> list[str]:
    cid = entry.get("component_id", "<missing>")
    errors = []
    if cid in seen:
        errors.append(f"{cid}: duplicate component id")
    seen.add(cid)
    errors.extend(_digest_errors(cid, entry))
    errors.extend(_predecessor_errors(cid, entry, ids))
    return errors


def _digest_errors(cid: str, entry: Mapping[str, Any]) -> list[str]:
    errors = []
    if not _COMMIT_RE.match(str(entry.get("source_commit", ""))):
        errors.append(f"{cid}: malformed or missing source commit")
    if not _DIGEST_RE.match(str(entry.get("artifact_digest", ""))):
        errors.append(f"{cid}: malformed or missing artifact digest")
    if not _DIGEST_RE.match(str(entry.get("profile_digest", ""))):
        errors.append(f"{cid}: malformed or missing profile digest")
    if entry.get("tag") and not entry.get("artifact_digest"):
        errors.append(f"{cid}: floating tag {entry['tag']!r} without a pinned digest")
    errors.extend(_provenance_errors(cid, entry))
    return errors


def _provenance_errors(cid: str, entry: Mapping[str, Any]) -> list[str]:
    receipt = entry.get("build_receipt")
    if receipt is None:
        return [f"{cid}: missing build/check receipt"]
    errors = []
    if receipt.get("source_commit") != entry.get("source_commit"):
        errors.append(f"{cid}: build receipt commit does not match the candidate's source commit")
    if receipt.get("artifact_digest") != entry.get("artifact_digest"):
        errors.append(f"{cid}: build receipt digest does not match the candidate's artifact digest")
    return errors


def _predecessor_errors(cid: str, entry: Mapping[str, Any], ids: Sequence[str]) -> list[str]:
    errors = []
    for predecessor in entry.get("predecessors", []):
        if predecessor == cid:
            errors.append(f"{cid}: self-referential predecessor")
        elif predecessor not in ids:
            errors.append(f"{cid}: unknown predecessor {predecessor!r}")
    return errors


def _cycle_errors(entries: Sequence[Mapping[str, Any]]) -> list[str]:
    graph = nx.DiGraph()
    for entry in entries:
        graph.add_node(entry.get("component_id", ""))
    for entry in entries:
        for predecessor in entry.get("predecessors", []):
            if predecessor in graph:
                graph.add_edge(predecessor, entry.get("component_id", ""))
    return [f"dependency cycle: {' -> '.join((*cycle, cycle[0]))}" for cycle in nx.simple_cycles(graph)]


def _build_candidate(entry: Mapping[str, Any]) -> Candidate:
    receipt = entry.get("build_receipt") or {}
    return Candidate(
        component_id=entry["component_id"],
        repository=entry.get("repository", ""),
        source_commit=entry["source_commit"],
        artifact_digest=entry["artifact_digest"],
        profile_digest=entry["profile_digest"],
        compatibility_range=entry.get("compatibility_range", ""),
        predecessors=tuple(entry.get("predecessors", [])),
        required_checks=tuple(entry.get("required_checks", [])),
        build_receipt=BuildReceipt(**receipt) if receipt else None,
        tag=entry.get("tag", ""),
    )
