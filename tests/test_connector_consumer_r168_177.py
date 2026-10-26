"""Immutable, test-only proof for PIPE-CONNSPEC consumer rows R168-R177.

The fixture shards preserve the bounded collector receipt for each consumer's
exact source SHA after the R118-R157 train landed. These tests replay captured
status metadata and assert canonical aggregate-hook evidence without invoking
consumer code or changing any consumer repository.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pipelines_hooks.cli import GROUPS


FIXTURE_DIR = Path(__file__).parent / "fixtures/connector_spec_delivery"
FIXTURES = sorted(FIXTURE_DIR.glob("consumer_train_r168_177_part*.json"))
EXPECTED_PROVIDER = "753086e0fd9783732ecd53eef0e08be8f6dd27c9"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_LEAVES = {"spec-status", "spec-decomposition", "spec-trailers"}
READY_SPEC_1 = {f"PIPE-CONNSPEC-R{i}.1" for i in range(168, 175)}
READY_SPEC_2 = {"PIPE-CONNSPEC-R168.2", "PIPE-CONNSPEC-R169.2", "PIPE-CONNSPEC-R171.2"}


def _evidence() -> dict:
    shards = [json.loads(path.read_text(encoding="utf-8")) for path in FIXTURES]
    assert len(shards) == 2
    evidence = dict(shards[0])
    evidence["repos"] = {}
    for shard in shards:
        assert shard["provider"] == evidence["provider"]
        assert shard["scope"] == evidence["scope"]
        evidence["repos"].update(shard["repos"])
    return evidence


@pytest.mark.spec("PIPE-CONNSPEC-R168.1")
@pytest.mark.spec("PIPE-CONNSPEC-R169.1")
@pytest.mark.spec("PIPE-CONNSPEC-R170.1")
@pytest.mark.spec("PIPE-CONNSPEC-R171.1")
@pytest.mark.spec("PIPE-CONNSPEC-R172.1")
@pytest.mark.spec("PIPE-CONNSPEC-R173.1")
@pytest.mark.spec("PIPE-CONNSPEC-R174.1")
def test_consumer_status_and_source_proof():
    evidence = _evidence()
    provider = evidence["provider"]
    assert provider["sha"] == EXPECTED_PROVIDER
    assert provider["canonical_template"]["rev"] == "main"
    assert set(provider["canonical_template"]["hooks"]) == EXPECTED_HOOKS
    assert provider["spec_group"]["aggregate_mapping_accepted"] is True
    assert provider["spec_group"]["aggregate_mapping_proven"] is True
    assert provider["spec_group"]["members"] == list(GROUPS["spec"])
    assert set(provider["spec_group"]["literal_requirement_hooks"]) == EXPECTED_SPEC_LEAVES
    assert set(evidence["repos"]) == {f"R{i}" for i in range(168, 178)}

    for name, row in evidence["repos"].items():
        spec_id = f"PIPE-CONNSPEC-{row['row']}.1"
        if spec_id not in READY_SPEC_1:
            continue
        assert row["leaves"][spec_id]["status"] == "READY", name
        assert len(row["sha"]) == 40 and all(char in "0123456789abcdef" for char in row["sha"])
        status = row["status"]
        assert status["ready"] is True, name
        assert status["errors"] == [], name
        assert status["record_error"] is None, name
        assert len(status["record_ids"]) == status["record_count"]
        assert status["record_count"] > 0
        for relative, document in status["status_documents"].items():
            assert relative in status["status_paths"], (name, relative)
            assert document["valid_schema"] is True, (name, relative)
            assert document["bytes"] > 0, (name, relative)
            assert len(document["sha256"]) == 64, (name, relative)

        required = {".github/workflows/pipeline.yml", ".github/workflows/pages.yml", ".pre-commit-config.yaml"}
        assert required <= set(row["source_files"]), name
        for relative, source in row["source_files"].items():
            if source is None:
                continue
            content = source["content"].encode()
            assert len(content) == source["bytes"], (name, relative)
            assert hashlib.sha256(content).hexdigest() == source["sha256"], (name, relative)


@pytest.mark.spec("PIPE-CONNSPEC-R168.2")
@pytest.mark.spec("PIPE-CONNSPEC-R169.2")
@pytest.mark.spec("PIPE-CONNSPEC-R171.2")
def test_consumer_aggregate_hooks_match_canonical_template():
    evidence = _evidence()
    qualified = {
        spec_id
        for row in evidence["repos"].values()
        for spec_id, leaf in row["leaves"].items()
        if spec_id.endswith(".2") and leaf["status"] == "READY"
    }
    assert qualified == READY_SPEC_2
    for row in evidence["repos"].values():
        spec_id = f"PIPE-CONNSPEC-{row['row']}.2"
        if spec_id not in qualified:
            continue
        hooks = row["precommit"]
        assert hooks["ready"] is True, row["row"]
        assert hooks["aggregate_mapping_accepted"] is True, row["row"]
        assert hooks["aggregate_mapping"] == list(GROUPS["spec"]), row["row"]
        assert hooks["aggregate_spec_present"] is True, row["row"]
        assert hooks["missing_template_hooks"] == [], row["row"]
        assert hooks["validate_config"]["rc"] == 0, row["row"]


def test_unqualified_rows_remain_explicitly_held():
    evidence = _evidence()
    for row in evidence["repos"].values():
        for suffix in (".3", ".4"):
            spec_id = f"PIPE-CONNSPEC-{row['row']}{suffix}"
            if spec_id in row["leaves"]:
                assert row["leaves"][spec_id]["status"] == "HELD"
    assert all(
        row["leaves"].get(f"PIPE-CONNSPEC-{row['row']}.1", {"status": "HELD"})["status"] != "READY"
        for row in evidence["repos"].values()
        if row["row"] in {"R175", "R176", "R177"}
    )
