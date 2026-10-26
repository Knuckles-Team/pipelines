"""Immutable, test-only proof for PIPE-CONNSPEC consumer rows R158-R167.

The fixture is the bounded collector receipt for each consumer's exact source
SHA after the R118-R157 train landed. These tests replay the existing status
reader and assert the captured canonical aggregate-hook evidence without
invoking consumer code or changing any consumer repository.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS
from scripts.spec_dashboard_sources import read_records


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r158_167.json"
EXPECTED_PROVIDER = "753086e0fd9783732ecd53eef0e08be8f6dd27c9"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_LEAVES = {"spec-status", "spec-decomposition", "spec-trailers"}
STATUS_CONFIG = {"sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _status_records(root: Path, row: dict) -> list[dict]:
    status = row["status"]
    for relative, content in status["status_source"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        assert hashlib.sha256(content.encode()).hexdigest() == status["status_file_sha256"][relative]
        assert json.loads(content) == status["status_documents"][relative]
    return read_records(root, STATUS_CONFIG)


@pytest.mark.spec("PIPE-CONNSPEC-R158.1")
@pytest.mark.spec("PIPE-CONNSPEC-R159.1")
@pytest.mark.spec("PIPE-CONNSPEC-R160.1")
@pytest.mark.spec("PIPE-CONNSPEC-R161.1")
@pytest.mark.spec("PIPE-CONNSPEC-R162.1")
@pytest.mark.spec("PIPE-CONNSPEC-R163.1")
@pytest.mark.spec("PIPE-CONNSPEC-R164.1")
@pytest.mark.spec("PIPE-CONNSPEC-R165.1")
@pytest.mark.spec("PIPE-CONNSPEC-R166.1")
@pytest.mark.spec("PIPE-CONNSPEC-R167.1")
def test_consumer_status_sources_are_readable(tmp_path: Path):
    evidence = _evidence()
    provider = evidence["provider"]
    assert provider["sha"] == EXPECTED_PROVIDER
    assert provider["spec_group"] == list(GROUPS["spec"])
    assert provider["spec_group_source"] == "pipelines_hooks/cli.py:71-74"
    for name, row in evidence["repos"].items():
        spec_id = f"{row['row']}.1"
        assert row["strict_leaves"][spec_id] is True, name
        assert len(row["sha"]) == 40 and all(char in "0123456789abcdef" for char in row["sha"])
        status = row["status"]
        records = _status_records(tmp_path / name, row)
        assert len(records) == status["status_record_count"]
        assert sorted(record["id"] for record in records) == sorted(status["status_spec_ids"])
        assert all(record["delivery_state"] in {"SPECIFIED", "LANDED", "VERIFIED"} for record in records)

        required = {".github/workflows/pipeline.yml", ".github/workflows/pages.yml", ".pre-commit-config.yaml"}
        assert required <= set(row["source_files"]), name
        for relative, source in row["source_files"].items():
            if source is None:
                continue
            content = source["content"].encode()
            assert len(content) == source["bytes"], (name, relative)
            assert hashlib.sha256(content).hexdigest() == source["sha256"], (name, relative)


@pytest.mark.spec("PIPE-CONNSPEC-R159.2")
@pytest.mark.spec("PIPE-CONNSPEC-R162.2")
@pytest.mark.spec("PIPE-CONNSPEC-R163.2")
@pytest.mark.spec("PIPE-CONNSPEC-R164.2")
@pytest.mark.spec("PIPE-CONNSPEC-R165.2")
@pytest.mark.spec("PIPE-CONNSPEC-R167.2")
def test_consumer_aggregate_hooks_match_canonical_template():
    evidence = _evidence()
    provider = evidence["provider"]
    assert set(provider["canonical_template"]["hooks"]) == EXPECTED_HOOKS
    assert provider["canonical_template"]["rev"] == "main"
    assert EXPECTED_SPEC_LEAVES <= set(GROUPS["spec"])
    expected = {name for name, row in evidence["repos"].items() if row["strict_leaves"].get(f"{row['row']}.2")}
    assert expected == {
        "salesforce-agent",
        "servicenow-api",
        "spark-mcp",
        "sql-mcp",
        "stirlingpdf-agent",
        "technitium-dns-mcp",
    }
    for name in expected:
        row = evidence["repos"][name]
        hooks = row["precommit"]
        assert hooks["aggregate_ready"] is True, name
        assert hooks["provider"] is True, name
        assert hooks["validate_config"]["returncode"] == 0, name
        assert hooks["canonical_hooks"] == provider["canonical_template"], name
        assert hooks["missing"] == [], name


@pytest.mark.parametrize("failed_gate", GROUPS["spec"])
def test_spec_aggregate_dispatches_every_member_and_propagates_failure(monkeypatch, failed_gate):
    calls: list[str] = []

    def fake_run_gate(gate: str, argv: list[str]) -> int:
        assert argv == []
        calls.append(gate)
        return 1 if gate == failed_gate else 0

    monkeypatch.setenv("PRE_COMMIT_FROM_REF", "HEAD")
    monkeypatch.delenv("SKIP", raising=False)
    monkeypatch.setattr("pipelines_hooks.cli.run_gate", fake_run_gate)

    from pipelines_hooks.cli import run_group

    assert run_group("spec", []) == 1
    assert calls == list(GROUPS["spec"])


def test_unqualified_rows_remain_explicitly_unbound():
    evidence = _evidence()
    assert evidence["strict_leaf_counts"] == {".1": 10, ".2": 6, ".3": 0, ".4": 0}
    assert all(not row["strict_leaves"].get(f"{row['row']}.3", False) for row in evidence["repos"].values())
    assert all(not row["strict_leaves"].get(f"{row['row']}.4", False) for row in evidence["repos"].values())
