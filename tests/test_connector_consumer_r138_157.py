"""Immutable, test-only proof for PIPE-CONNSPEC consumer rows R138-R157.

The fixture is the bounded collector receipt for each consumer's exact source
SHA. These tests replay the existing status metadata and assert the captured
canonical aggregate-hook and hosted Pages evidence without invoking consumer
code or changing any consumer repository.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE_DIR = Path(__file__).parent / "fixtures/connector_spec_delivery"
FIXTURES = sorted(FIXTURE_DIR.glob("consumer_train_r138_157_part*.json"))
EXPECTED_PROVIDER = "5a4414da360c2f500c898a24bde103f535d10514"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_LEAVES = {"spec-status", "spec-decomposition", "spec-trailers"}
READY_SPEC_2 = {
    "PIPE-CONNSPEC-R138.2",
    "PIPE-CONNSPEC-R141.2",
    "PIPE-CONNSPEC-R144.2",
    "PIPE-CONNSPEC-R145.2",
    "PIPE-CONNSPEC-R146.2",
    "PIPE-CONNSPEC-R148.2",
    "PIPE-CONNSPEC-R149.2",
    "PIPE-CONNSPEC-R153.2",
    "PIPE-CONNSPEC-R154.2",
    "PIPE-CONNSPEC-R156.2",
}
READY_SPEC_3 = {
    "PIPE-CONNSPEC-R140.3",
    "PIPE-CONNSPEC-R147.3",
    "PIPE-CONNSPEC-R148.3",
    "PIPE-CONNSPEC-R157.3",
} | {"PIPE-CONNSPEC-R154.3"}


def _evidence() -> dict:
    shards = [json.loads(path.read_text(encoding="utf-8")) for path in FIXTURES]
    assert len(shards) == 4
    evidence = dict(shards[0])
    evidence["repos"] = {}
    for shard in shards:
        assert shard["provider"] == evidence["provider"]
        assert shard["scope"] == evidence["scope"]
        evidence["repos"].update(shard["repos"])
    return evidence


@pytest.mark.spec("PIPE-CONNSPEC-R138.1")
@pytest.mark.spec("PIPE-CONNSPEC-R139.1")
@pytest.mark.spec("PIPE-CONNSPEC-R140.1")
@pytest.mark.spec("PIPE-CONNSPEC-R141.1")
@pytest.mark.spec("PIPE-CONNSPEC-R142.1")
@pytest.mark.spec("PIPE-CONNSPEC-R143.1")
@pytest.mark.spec("PIPE-CONNSPEC-R144.1")
@pytest.mark.spec("PIPE-CONNSPEC-R145.1")
@pytest.mark.spec("PIPE-CONNSPEC-R146.1")
@pytest.mark.spec("PIPE-CONNSPEC-R147.1")
@pytest.mark.spec("PIPE-CONNSPEC-R148.1")
@pytest.mark.spec("PIPE-CONNSPEC-R149.1")
@pytest.mark.spec("PIPE-CONNSPEC-R150.1")
@pytest.mark.spec("PIPE-CONNSPEC-R151.1")
@pytest.mark.spec("PIPE-CONNSPEC-R152.1")
@pytest.mark.spec("PIPE-CONNSPEC-R153.1")
@pytest.mark.spec("PIPE-CONNSPEC-R154.1")
@pytest.mark.spec("PIPE-CONNSPEC-R155.1")
@pytest.mark.spec("PIPE-CONNSPEC-R156.1")
@pytest.mark.spec("PIPE-CONNSPEC-R157.1")
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

    assert set(evidence["repos"]) == {f"R{i}" for i in range(138, 158)}
    for name, row in evidence["repos"].items():
        assert len(row["sha"]) == 40 and all(char in "0123456789abcdef" for char in row["sha"])
        spec_id = f"PIPE-CONNSPEC-{row['row']}.1"
        assert row["leaves"][spec_id]["status"] == "READY", name
        status = row["status"]
        assert status["ready"] is True, name
        assert status["errors"] == [], name
        assert status["record_error"] is None, name
        assert len(status["record_ids"]) == status["record_count"], name
        assert status["record_count"] > 0, name
        for relative, document in status["status_documents"].items():
            assert relative in status["status_paths"], (name, relative)
            assert document["valid_schema"] is True, (name, relative)
            assert document["bytes"] > 0, (name, relative)
            assert len(document["sha256"]) == 64, (name, relative)

        required = {
            ".github/workflows/pipeline.yml",
            ".github/workflows/pages.yml",
            ".pre-commit-config.yaml",
        }
        assert required <= set(row["source_files"]), name
        for relative, source in row["source_files"].items():
            if source is None:
                continue
            content = source["content"].encode()
            assert len(content) == source["bytes"], (name, relative)
            assert hashlib.sha256(content).hexdigest() == source["sha256"], (name, relative)


@pytest.mark.spec("PIPE-CONNSPEC-R138.2")
@pytest.mark.spec("PIPE-CONNSPEC-R141.2")
@pytest.mark.spec("PIPE-CONNSPEC-R144.2")
@pytest.mark.spec("PIPE-CONNSPEC-R145.2")
@pytest.mark.spec("PIPE-CONNSPEC-R146.2")
@pytest.mark.spec("PIPE-CONNSPEC-R148.2")
@pytest.mark.spec("PIPE-CONNSPEC-R149.2")
@pytest.mark.spec("PIPE-CONNSPEC-R153.2")
@pytest.mark.spec("PIPE-CONNSPEC-R154.2")
@pytest.mark.spec("PIPE-CONNSPEC-R156.2")
def test_consumer_aggregate_hooks_match_canonical_template():
    evidence = _evidence()
    qualified = {
        spec_id
        for row in evidence["repos"].values()
        for spec_id, leaf in row["leaves"].items()
        if spec_id.endswith(".2") and leaf["status"] == "READY"
    }
    assert qualified == READY_SPEC_2
    for name, row in evidence["repos"].items():
        spec_id = f"PIPE-CONNSPEC-{row['row']}.2"
        if spec_id not in qualified:
            continue
        hooks = row["precommit"]
        assert hooks["ready"] is True, name
        assert hooks["aggregate_mapping_accepted"] is True, name
        assert hooks["aggregate_mapping"] == list(GROUPS["spec"]), name
        assert hooks["aggregate_spec_present"] is True, name
        assert hooks["missing_template_hooks"] == [], name
        assert hooks["validate_config"]["rc"] == 0, name
        assert hooks["provider_rev"] == "main", name


@pytest.mark.spec("PIPE-CONNSPEC-R140.3")
@pytest.mark.spec("PIPE-CONNSPEC-R147.3")
@pytest.mark.spec("PIPE-CONNSPEC-R148.3")
@pytest.mark.spec("PIPE-CONNSPEC-R157.3")
def test_consumer_pages_are_current_and_published():
    evidence = _evidence()
    qualified = {
        spec_id
        for row in evidence["repos"].values()
        for spec_id, leaf in row["leaves"].items()
        if spec_id.endswith(".3") and leaf["status"] == "READY"
    }
    assert qualified == READY_SPEC_3
    for row in evidence["repos"].values():
        spec_id = f"PIPE-CONNSPEC-{row['row']}.3"
        if spec_id not in qualified:
            continue
        pages = row["pages"]
        run = pages["hosted_run"]
        assert pages["caller_count"] == 1
        assert pages["missing_required_paths"] == []
        assert pages["with"]["content_source"] == "docs"
        assert pages["with"]["spec_dashboard_enabled"] is True
        assert pages["with"]["spec_dashboard_config"] in {".github/spec-dashboard.json", ".config/spec-dashboard.json"}
        assert pages["config"]["version"] == 1
        assert pages["config"]["valid"] is True
        assert run["conclusion"] == "success"
        assert run["headSha"] == row["sha"]
        assert run["url"].startswith(f"https://github.com/Knuckles-Team/{row['workspace_repo']}/actions/runs/")
        assert pages["http"]["status"] == 200
        assert pages["http"]["has_spec_id"] is True
        assert pages["http"]["url"].endswith("/spec-delivery/")


def test_unqualified_rows_remain_explicitly_held():
    evidence = _evidence()
    states = {
        suffix: sum(
            leaf["status"] == "READY"
            for row in evidence["repos"].values()
            for spec_id, leaf in row["leaves"].items()
            if spec_id.endswith(suffix)
        )
        for suffix in (".1", ".2", ".3", ".4")
    }
    assert states == {".1": 20, ".2": 10, ".3": 5, ".4": 1}
    assert states[".4"] == 1


@pytest.mark.spec("PIPE-CONNSPEC-R154.3")
def test_postiz_pages_are_current_and_published():
    row = _evidence()["repos"]["R154"]
    pages = row["pages"]
    assert row["leaves"]["PIPE-CONNSPEC-R154.3"]["status"] == "READY"
    assert pages["caller_count"] == 1
    assert pages["with"]["content_source"] == "docs"
    assert pages["with"]["spec_dashboard_enabled"] is True
    assert pages["with"]["spec_dashboard_config"] == ".config/spec-dashboard.json"
    assert pages["config"]["valid"] is True
    assert pages["hosted_run"]["headSha"] == row["sha"]
    assert pages["hosted_run"]["databaseId"] == 40426272448
    assert pages["http"]["status"] == 200
    assert pages["http"]["sha256"] == "c47e53d51fc8e29eb447f62e46afb663a116db31ad22d64f46ece5b2ea4fe0d8"


@pytest.mark.spec("PIPE-CONNSPEC-R154.4")
def test_postiz_development_skill_is_source_backed():
    row = _evidence()["repos"]["R154"]
    skill = row["skills"]
    assert row["leaves"]["PIPE-CONNSPEC-R154.4"]["status"] == "READY"
    assert skill["ready"] is True
    assert skill["present"] is True
    assert skill["path"] == "postiz_agent/skills/postiz-agent-development/SKILL.md"
    assert skill["matches"] == [skill["path"]]
    source = row["source_files"][skill["path"]]
    assert source["sha256"] == skill["source_sha256"]
    assert skill["phrase"] in source["content"]
