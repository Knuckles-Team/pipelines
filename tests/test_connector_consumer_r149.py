"""Immutable source-bound proof for Lucerna's R149.3/.4 adoption."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS

FIXTURE = Path(__file__).parent / "fixtures" / "connector_spec_delivery" / "consumer_train_r149.json"
EXPECTED_PROVIDER = "b6eae5ebbcd03ed2463c80b891038cc4990e782a"
EXPECTED_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_STATUS = "fcaead3ab9ea023b278203f24cb352888f39cf1aff3a40de13a0ff7247eebda7"
EXPECTED_CONSUMER = {
    "merge": "c17488ee8fd16c3ed134426a94772be20478109e",
    "pages_run": 40415397427,
    "records": 2,
    "repo_url": "https://knuckles-team.github.io/lucerna-mcp/",
    "dashboard": ".config/spec-dashboard.json",
    "skill": "lucerna_mcp/skills/lucerna-mcp-development/SKILL.md",
}
EXPECTED_ROWS = {"PIPE-CONNSPEC-R149.3", "PIPE-CONNSPEC-R149.4"}
EXPECTED_HISTORICAL = {"PIPE-CONNSPEC-R149.1", "PIPE-CONNSPEC-R149.2"}
EXPECTED_HOOKS = {"connector-standard", "dependency-readiness", "secrets", "spec", "tests-fast"}
EXPECTED_SPEC_MEMBERS = {"spec-standard", "plan-conformance", "spec-decomposition", "spec-status", "spec-trailers"}


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _bytes(document: dict) -> bytes:
    data = base64.b64decode(document["data"])
    assert len(data) == document["bytes"]
    assert hashlib.sha256(data).hexdigest() == document["sha256"]
    return data


@pytest.mark.spec("PIPE-CONNSPEC-R149.3")
@pytest.mark.spec("PIPE-CONNSPEC-R149.4")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert set(evidence["repos"]) == {"lucerna-mcp"}
    assert evidence["scope"] == sorted(EXPECTED_ROWS)
    assert evidence["target_rows"] == sorted(EXPECTED_ROWS)
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 0, ".3": 1, ".4": 1}
    assert evidence["qualification"] == {
        "already_qualified_dot_one_recounted": False,
        "already_qualified_dot_two_recounted": False,
        "rollups_promoted": False,
        "source_release_success_claimed": False,
        "held_rows_included": [],
        "generic_rows_included": [],
    }
    row = evidence["repos"]["lucerna-mcp"]
    assert row["sha"] == row["candidate_sha"] == EXPECTED_CONSUMER["merge"]
    assert set(row["historical_verified_leaves"]) == EXPECTED_HISTORICAL
    assert not set(row["historical_verified_leaves"]) & EXPECTED_ROWS
    assert set(row["strict_leaves"]) == EXPECTED_ROWS
    assert all(row["strict_leaves"].values())


def test_provider_mapping_and_baseline_status_are_immutable() -> None:
    evidence = _evidence()
    provider = evidence["provider"]
    assert provider["requirements_sha256"] == EXPECTED_REQUIREMENTS
    assert provider["status_sha256"] == EXPECTED_STATUS
    for document in provider["source_files"].values():
        _bytes(document)
    provider_status = json.loads(_bytes(provider["source_files"]["status.json"]))
    assert hashlib.sha256(_bytes(provider["source_files"]["requirements.md"])).hexdigest() == EXPECTED_REQUIREMENTS
    assert hashlib.sha256(_bytes(provider["source_files"]["status.json"])).hexdigest() == EXPECTED_STATUS
    assert (
        hashlib.sha256(_bytes(provider["source_files"]["pre-commit-template.yaml"])).hexdigest()
        == provider["canonical_template"]["sha256"]
    )
    assert provider["canonical_template"]["rev"] == "main"
    assert set(provider["canonical_template"]["hooks"]) == EXPECTED_HOOKS
    assert provider["spec_group"]["aggregate_mapping_accepted"] is True
    assert provider["spec_group"]["aggregate_mapping_proven"] is True
    assert set(provider["spec_group"]["members"]) == EXPECTED_SPEC_MEMBERS
    assert provider["spec_group"]["members"] == list(GROUPS["spec"])
    baseline = {row["id"]: row for row in provider_status["requirements"]}
    assert evidence["central_requirements"] == {
        row_id: baseline[row_id] for row_id in sorted(evidence["central_requirements"])
    }
    for requirement_id in EXPECTED_ROWS:
        current = baseline[requirement_id]
        assert current["delivery_state"] == "SPECIFIED"
        assert current["landed_in"] == []
        assert current["verified_by"] == []
    for requirement_id in EXPECTED_HISTORICAL:
        current = baseline[requirement_id]
        assert current["delivery_state"] == "VERIFIED"
        assert current["landed_in"]
        assert current["verified_by"]


def test_consumer_source_and_status_snapshots_match_declared_hashes() -> None:
    evidence = _evidence()
    row = evidence["repos"]["lucerna-mcp"]
    required = {
        EXPECTED_CONSUMER["dashboard"],
        ".github/workflows/pages.yml",
        ".github/workflows/pipeline.yml",
        ".pre-commit-config.yaml",
        "docs/index.md",
        EXPECTED_CONSUMER["skill"],
    }
    assert required <= set(row["source_files"])
    assert row["source_paths"] == {path: path for path in row["source_files"]}
    assert row["status_paths"] == {path: path for path in row["status_files"]}
    for document in row["source_files"].values():
        _bytes(document)
    for relative, document in row["status_files"].items():
        parsed = json.loads(_bytes(document))
        assert parsed["schema_version"] == 2, relative
        assert parsed["requirements"], relative


@pytest.mark.spec("PIPE-CONNSPEC-R149.3")
def test_pages_are_exact_merged_source_published() -> None:
    evidence = _evidence()
    row = evidence["repos"]["lucerna-mcp"]
    pages = row["pages"]
    assert pages["strict_ready"] is True
    assert pages["caller_count"] == 1
    assert pages["exact_source_publisher_ready"] is True
    hosted = pages["hosted_run"]
    assert hosted["databaseId"] == EXPECTED_CONSUMER["pages_run"]
    assert hosted["conclusion"] == "success"
    assert hosted["headSha"] == EXPECTED_CONSUMER["merge"]
    assert hosted["workflowName"] == "Deploy GitHub Pages"
    assert pages["with"] == {
        "content_source": "docs",
        "spec_dashboard_enabled": True,
        "spec_dashboard_config": EXPECTED_CONSUMER["dashboard"],
    }
    api = pages["pages_api"]
    assert api["html_url"] == EXPECTED_CONSUMER["repo_url"]
    assert api["public"] is True
    assert api["https_enforced"] is True
    assert pages["index_url"] == f"{EXPECTED_CONSUMER['repo_url']}spec-delivery/index.html"
    assert pages["snapshot_url"] == f"{EXPECTED_CONSUMER['repo_url']}spec-delivery/snapshot.json"
    index_content = _bytes(pages["index.html"]["body"])
    snapshot_content = _bytes(pages["snapshot.json"]["body"])
    assert index_content and b"lucerna-mcp" in index_content
    parsed = json.loads(snapshot_content)
    assert pages["snapshot_revision"] == EXPECTED_CONSUMER["merge"]
    assert pages["snapshot_repository"] == "Knuckles-Team/lucerna-mcp"
    assert pages["snapshot_record_count"] == len(parsed["records"]) == EXPECTED_CONSUMER["records"]
    assert parsed["revision"] == EXPECTED_CONSUMER["merge"]
    assert parsed["repository"] == "Knuckles-Team/lucerna-mcp"
    assert {record["id"] for record in parsed["records"]} == {
        "CONN-LUCERNA-MCP-CONNECTOR-CONTENT",
        "CONN-LUCERNA-MCP-CONNECTOR-CONTENT-R001",
    }


@pytest.mark.spec("PIPE-CONNSPEC-R149.4")
def test_skill_contract_is_substantive_and_path_bound() -> None:
    evidence = _evidence()
    row = evidence["repos"]["lucerna-mcp"]
    skill = _bytes(row["source_files"][EXPECTED_CONSUMER["skill"]]).decode()
    workflow = _bytes(row["source_files"][".github/workflows/pages.yml"]).decode()
    dashboard = json.loads(_bytes(row["source_files"][EXPECTED_CONSUMER["dashboard"]]))
    docs_index = _bytes(row["source_files"]["docs/index.md"]).decode()
    assert re.search(r"^## Rapid delivery: the 5-minute contract$", skill, re.MULTILINE)
    for term in row["skill_terms"]:
        assert term.lower() in skill.lower(), term
    assert "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main" in workflow
    assert "workflow_dispatch:" in workflow
    assert "content_source: docs" in workflow
    assert "spec_dashboard_enabled: true" in workflow
    assert "spec_dashboard_config: .config/spec-dashboard.json" in workflow
    assert dashboard == {"version": 1, "sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}
    assert "spec-delivery/" in docs_index


def test_release_success_is_never_claimed() -> None:
    evidence = _evidence()
    assert evidence["qualification"]["source_release_success_claimed"] is False
    assert not evidence["repos"]["lucerna-mcp"]["release"]["evidence_claimed"]


def test_fixture_cannot_create_false_json_test_bindings() -> None:
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    assert "mark.spec(" not in fixture_text
    assert "# spec:" not in fixture_text


@pytest.mark.spec("PIPE-CONNSPEC-R149.3")
def test_requirement_repo_identity_is_the_canonical_rename() -> None:
    identity = _evidence()["repos"]["lucerna-mcp"]["identity"]
    assert identity["requested_repo"] == "Knuckles-Team/opensearch-mcp"
    assert identity["canonical_repo"] == "Knuckles-Team/lucerna-mcp"
    assert identity["requested_api_full_name"] == identity["canonical_api_full_name"] == identity["canonical_repo"]
    assert identity["redirect_location"] == "https://github.com/Knuckles-Team/lucerna-mcp"
    assert identity["requested_main_sha"] == identity["canonical_main_sha"] == EXPECTED_CONSUMER["merge"]
    assert identity["pages_url"] == EXPECTED_CONSUMER["repo_url"]
