"""test-quality verifies a graph-to-Meristem-to-ingestion acceptance receipt; it never orchestrates a run."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.code import graph_workflow_receipt as receipt_gate
from pipelines_hooks.code.test_quality import RULES
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import HOOK_REPOSITORY, Repo

IDENTITIES = ["node:1", "node:2"]
GOOD = {
    "run_id": "run-1",
    "producer_revisions": {"medulla": "m1", "meristem": "a1", "scion-sdk": "s1"},
    "workflow_identity": "wf-1",
    "graph_revision": "g7",
    "graph_load": {"run_id": "run-1", "source": "real"},
    "decision": {"run_id": "run-1", "id": "dec-1", "workflow_identity": "wf-1"},
    "execution": {"run_id": "run-1", "steps": ["s1", "s2"]},
    "ingestion": {"run_id": "run-1", "committed": True, "transaction": "tx-1"},
    "readback": {
        "run_id": "run-1",
        "independent": True,
        "query": "hydrated(wf-1)",
        "expected_identities": IDENTITIES,
        "observed_digest": hashlib.sha256(json.dumps(sorted(IDENTITIES)).encode()).hexdigest(),
    },
    "source_effects": {"scion-sdk": "applied"},
}


def _fixture(repo: Repo, tmp_path: Path, receipt: dict) -> Path:
    repo.commit(
        {
            "coverage.json": json.dumps({"totals": {"percent_covered": 99}}),
            "tests/test_a.py": "def test_a():\n    assert 1 == 1\n",
        }
    )
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    return path


def _run(repo: Repo, path: Path, *extra: str) -> int:
    return repo.run("test-quality", "--graph-workflow-receipt", str(path), *extra)


def _broken(**changes: object) -> dict:
    document = copy.deepcopy(GOOD)
    document.update(changes)
    return document


@pytest.mark.spec("PIPE-PAGES-R021.73")
def test_graph_workflow_receipt_model(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    path.write_text(json.dumps(GOOD))
    loaded = receipt_gate.load(path)
    assert (loaded.workflow_identity, loaded.graph_revision, loaded.run_id) == ("wf-1", "g7", "run-1")
    assert loaded.decision["id"] == "dec-1" and loaded.execution["steps"] == ["s1", "s2"]
    assert loaded.ingestion["transaction"] == "tx-1" and loaded.readback["observed_digest"]
    assert receipt_gate.check(path).findings == []  # one end-to-end run identity binds every part


@pytest.mark.spec("PIPE-PAGES-R021.74")
def test_graph_workflow_receipt_behavior(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    for field_name, change, expected in (
        ("graph_load", {"run_id": "run-1", "source": "cache"}, "not the real graph"),
        ("ingestion", {"run_id": "run-1", "committed": False}, "not committed"),
        ("decision", {"run_id": "run-1", "id": "d", "workflow_identity": "other"}, "different workflow"),
        ("readback", {**GOOD["readback"], "observed_digest": "0"}, "digest differs"),
    ):
        path.write_text(json.dumps(_broken(**{field_name: change})))
        details = [d for _, _, d in receipt_gate.check(path).findings]
        assert any(expected in d for d in details), (field_name, details)


@pytest.mark.spec("PIPE-PAGES-R021.75")
def test_graph_workflow_receipt_wiring() -> None:
    assert GATES["test-quality"] == "pipelines_hooks.code.test_quality"
    assert "pipelines-hook test-quality" in (HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text()
    assert "handoff-receipt-invalid" in RULES
    assert not hasattr(receipt_gate, "run_workflow")  # the gate verifies provenance; it is no orchestrator


@pytest.mark.spec("PIPE-PAGES-R021.76")
def test_graph_workflow_receipt_refusal(repo: Repo, tmp_path: Path, capsys) -> None:
    path = _fixture(repo, tmp_path, _broken(graph_load={}))
    assert _run(repo, path) == 1  # missing graph-load evidence
    assert "graph_load evidence is missing" in capsys.readouterr().out
    path.write_text(json.dumps(_broken(execution={"run_id": "run-2", "steps": []})))
    assert _run(repo, path) == 1  # mismatched run identities
    path.write_text(json.dumps(_broken(readback={})))
    assert _run(repo, path) == 1  # no independent readback
    path.write_text(json.dumps(_broken(graph_load={"run_id": "run-1", "source": "mock"})))
    assert _run(repo, path) == 1  # a mocked catalog is not a graph load
    assert _run(repo, tmp_path / "absent.json") == 2  # unavailable real components
    path.write_text(json.dumps(GOOD))
    assert _run(repo, path, "--expect-revision", "medulla=m0") == 2  # a stale source binding
    with pytest.raises(CannotRun):
        receipt_gate.check(path, {"meristem": "old"})


@pytest.mark.spec("PIPE-PAGES-R021.77")
def test_graph_workflow_receipt_evidence(repo: Repo, tmp_path: Path) -> None:
    path = _fixture(repo, tmp_path, _broken(failure={"kind": "cancelled", "step": "s2"}))
    out = tmp_path / "evidence.json"
    assert _run(repo, path, "--evidence", str(out)) == 0
    evidence = json.loads(out.read_text())["graph_workflow"]
    assert evidence["producer_revisions"]["medulla"] == "m1" and evidence["workflow_identity"] == "wf-1"
    assert evidence["selected_decision"] == "dec-1" and evidence["executed_steps"] == ["s1", "s2"]
    assert evidence["ingestion_receipt"] == "tx-1" and evidence["readback"]["expected"] == IDENTITIES
    assert evidence["source_effects"] == {"scion-sdk": "applied"}  # kept apart from graph durability
    assert evidence["failure"] == {"kind": "cancelled", "step": "s2"}  # cancellation evidence is retained


@pytest.mark.spec("PIPE-PAGES-R021.78")
def test_graph_workflow_receipt_cli(repo: Repo, tmp_path: Path) -> None:
    path = _fixture(repo, tmp_path, GOOD)
    assert _run(repo, path) == 0
    for name, broken in (
        ("no readback", _broken(readback={})),
        ("fake catalog", _broken(graph_load={"run_id": "run-1", "source": "fake-catalog"})),
        ("decision mismatch", _broken(decision={"run_id": "run-1", "id": "d", "workflow_identity": "wf-x"})),
    ):
        path.write_text(json.dumps(broken))
        assert _run(repo, path) == 1, name
