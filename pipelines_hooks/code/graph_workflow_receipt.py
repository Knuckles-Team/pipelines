"""Graph-to-execution-to-ingestion handoff receipt for ``test-quality`` (PIPE-PAGES-R021.73 to .78).

The owner acceptance run loads a persisted workflow from the real graph, takes an engine decision,
executes it through the harness, ingests the result through the owner boundary and reads the hydrated
identities back with an independent client. This module only *verifies* that receipt; it never
orchestrates a run. Every component must carry the one run identity, the graph load must come from
the real graph, the ingestion must be committed and the readback must be independent and match.
A missing or unreadable receipt, or one bound to a stale producer revision, is ``CannotRun``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

RULE = "handoff-receipt-invalid"
COMPONENTS = ("graph_load", "decision", "execution", "ingestion", "readback")


@dataclass(frozen=True)
class GraphWorkflowReceipt:
    run_id: str
    producer_revisions: dict[str, str]
    workflow_identity: str
    graph_revision: str
    graph_load: dict
    decision: dict
    execution: dict
    ingestion: dict
    readback: dict
    source_effects: dict = field(default_factory=dict)  # governed source effects, kept apart from graph durability
    failure: dict | None = None  # failure or cancellation evidence, retained rather than dropped


@dataclass
class HandoffResult:
    findings: list[tuple[str, int, str]] = field(default_factory=list)
    evidence: dict[str, object] = field(default_factory=dict)


def load(path: Path) -> GraphWorkflowReceipt:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return GraphWorkflowReceipt(
            run_id=data["run_id"],
            producer_revisions=dict(data["producer_revisions"]),
            workflow_identity=data["workflow_identity"],
            graph_revision=data["graph_revision"],
            graph_load=data.get("graph_load") or {},
            decision=data.get("decision") or {},
            execution=data.get("execution") or {},
            ingestion=data.get("ingestion") or {},
            readback=data.get("readback") or {},
            source_effects=data.get("source_effects") or {},
            failure=data.get("failure"),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CannotRun(f"handoff receipt {path} is unavailable or unreadable: {exc!r}") from exc


def _digest(identities: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(identities)).encode()).hexdigest()


def _run_findings(receipt: GraphWorkflowReceipt) -> list[str]:
    found = [
        f"{name} carries run {getattr(receipt, name).get('run_id')!r}, not {receipt.run_id!r}"
        for name in COMPONENTS
        if getattr(receipt, name) and getattr(receipt, name).get("run_id") != receipt.run_id
    ]
    found += [f"{name} evidence is missing" for name in COMPONENTS if not getattr(receipt, name)]
    return found


def _outcome_findings(receipt: GraphWorkflowReceipt) -> list[str]:
    found = []
    if receipt.graph_load and receipt.graph_load.get("source") != "real":
        found.append(f"graph load came from {receipt.graph_load.get('source')!r}, not the real graph")
    if receipt.decision and receipt.decision.get("workflow_identity") != receipt.workflow_identity:
        found.append("the engine decision names a different workflow identity")
    if receipt.ingestion and not receipt.ingestion.get("committed"):
        found.append("the ingestion transaction is not committed")
    reading = receipt.readback
    if reading and reading.get("independent") is not True:
        found.append("the readback is not from an independent client")
    elif reading and reading.get("observed_digest") != _digest(list(reading.get("expected_identities") or [])):
        found.append("the readback digest differs from the expected hydrated identities")
    return found


def check(path: Path, expected_revisions: dict[str, str] | None = None) -> HandoffResult:
    receipt = load(path)
    for producer, revision in (expected_revisions or {}).items():
        if receipt.producer_revisions.get(producer) != revision:
            raise CannotRun(f"handoff receipt is bound to a stale {producer} revision")
    found = _run_findings(receipt) + _outcome_findings(receipt)
    evidence = {
        "run_id": receipt.run_id,
        "producer_revisions": receipt.producer_revisions,
        "workflow_identity": receipt.workflow_identity,
        "graph_revision": receipt.graph_revision,
        "selected_decision": receipt.decision.get("id"),
        "executed_steps": receipt.execution.get("steps", []),
        "ingestion_receipt": receipt.ingestion.get("transaction"),
        "readback": {
            "query": receipt.readback.get("query"),
            "expected": receipt.readback.get("expected_identities"),
            "observed_digest": receipt.readback.get("observed_digest"),
        },
        "source_effects": receipt.source_effects,
        "failure": receipt.failure,
    }
    return HandoffResult([(str(path), 0, item) for item in found], evidence)
