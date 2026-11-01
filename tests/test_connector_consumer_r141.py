"""Source-bound proof for the genuinely new Mealie R141.3/.4 leaves.

R141.1 and R141.2 are historical verified evidence at the provider baseline.
This test qualifies only the merged Pages caller and substantive development
skill, with exact source and hosted Pages snapshots captured in the fixture.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r141.json"
EXPECTED_PROVIDER = "aa8ee4b58c58b1dc3ad3b078aa43fd10ee41e947"
EXPECTED_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_STATUS = "f691f5caf71d40a2e6d72a22631d8e4432b7b8a5121a2c9218d4a1c57f9d6386"
EXPECTED_CONSUMER = "a0a9b313aadf7d7ebd45fd6038bdb9df503eb5b3"
EXPECTED_MERGE = "a0a9b313aadf7d7ebd45fd6038bdb9df503eb5b3"
EXPECTED_PAGES_RUN = 40405383602
EXPECTED_ROWS = {"PIPE-CONNSPEC-R141.3", "PIPE-CONNSPEC-R141.4"}
EXPECTED_HISTORICAL = {"PIPE-CONNSPEC-R141.1", "PIPE-CONNSPEC-R141.2"}
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_MEMBERS = {
    "spec-standard",
    "plan-conformance",
    "spec-decomposition",
    "spec-status",
    "spec-trailers",
}
EXPECTED_SKILL = "mealie_mcp/skills/mealie-mcp-development/SKILL.md"


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _bytes(document: dict) -> bytes:
    assert document["encoding"] == "base64"
    content = base64.b64decode(document["data"], validate=True)
    assert len(content) == document["bytes"]
    assert hashlib.sha256(content).hexdigest() == document["sha256"]
    return content


def _qualified(evidence: dict) -> dict[str, dict]:
    return {
        requirement_id: {"repo": repo, "data": row}
        for repo, row in evidence["repos"].items()
        for requirement_id, ready in row["strict_leaves"].items()
        if ready
    }


@pytest.mark.spec("PIPE-CONNSPEC-R141.3")
@pytest.mark.spec("PIPE-CONNSPEC-R141.4")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert set(evidence["repos"]) == {"mealie-mcp"}
    assert set(_qualified(evidence)) == EXPECTED_ROWS
    assert evidence["scope"] == sorted(EXPECTED_ROWS)
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 0, ".3": 1, ".4": 1}
    assert evidence["qualification"] == {
        "already_qualified_dot_one_recounted": False,
        "already_qualified_dot_two_recounted": False,
        "rollups_promoted": False,
        "source_release_success_claimed": False,
        "held_rows_included": [],
        "generic_rows_included": [],
    }
    row = evidence["repos"]["mealie-mcp"]
    assert row["sha"] == row["candidate_sha"] == EXPECTED_CONSUMER
    assert set(row["historical_verified_leaves"]) == EXPECTED_HISTORICAL
    assert not EXPECTED_HISTORICAL & EXPECTED_ROWS


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
    assert provider["spec_group"]["members"] == list(GROUPS["spec"])
    assert set(provider["spec_group"]["members"]) == EXPECTED_SPEC_MEMBERS
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
    row = evidence["repos"]["mealie-mcp"]
    required = {
        ".github/spec-dashboard.json",
        ".github/workflows/pages.yml",
        ".pre-commit-config.yaml",
        "docs/index.md",
        EXPECTED_SKILL,
    }
    assert required <= set(row["source_files"])
    assert row["source_paths"] == {path: path for path in row["source_files"]}
    assert row["status_paths"] == {path: path for path in row["status_files"]}
    for document in row["source_files"].values():
        _bytes(document)
    for relative, document in row["status_files"].items():
        parsed = json.loads(_bytes(document))
        assert parsed["schema_version"] == 2, relative
        if relative != "specs/_template/status.json":
            assert parsed["requirements"], relative


@pytest.mark.spec("PIPE-CONNSPEC-R141.3")
def test_pages_are_exact_merged_source_published() -> None:
    evidence = _evidence()
    row = evidence["repos"]["mealie-mcp"]
    pages = row["pages"]
    assert pages["strict_ready"] is True
    assert pages["caller_count"] == 1
    assert pages["exact_source_publisher_ready"] is True
    hosted = pages["hosted_run"]
    assert hosted["id"] == EXPECTED_PAGES_RUN
    assert hosted["conclusion"] == "success"
    assert hosted["headSha"] == EXPECTED_MERGE
    assert hosted["workflowName"] == "publish-pages"
    assert pages["with"] == {
        "content_source": "docs",
        "spec_dashboard_enabled": True,
        "spec_dashboard_config": ".github/spec-dashboard.json",
    }
    api = pages["pages_api"]
    assert api["html_url"] == "https://knuckles-team.github.io/mealie-mcp/"
    assert api["build_type"] == "workflow"
    assert api["public"] is True
    assert api["https_enforced"] is True
    assert api["source"] == {"branch": "main", "path": "/"}
    assert pages["index_url"] == "https://knuckles-team.github.io/mealie-mcp/spec-delivery/index.html"
    assert pages["snapshot_url"] == "https://knuckles-team.github.io/mealie-mcp/spec-delivery/snapshot.json"
    index_content = _bytes(pages["index.html"]["body"])
    snapshot_content = _bytes(pages["snapshot.json"]["body"])
    assert index_content
    parsed = json.loads(snapshot_content)
    assert pages["snapshot_revision"] == EXPECTED_MERGE
    assert pages["snapshot_repository"] == "Knuckles-Team/mealie-mcp"
    assert pages["snapshot_record_count"] == len(parsed["records"]) == 2
    assert parsed["revision"] == EXPECTED_MERGE
    assert parsed["repository"] == "Knuckles-Team/mealie-mcp"
    assert parsed["records"]


@pytest.mark.spec("PIPE-CONNSPEC-R141.4")
def test_skill_contract_is_substantive_and_path_bound() -> None:
    evidence = _evidence()
    row = evidence["repos"]["mealie-mcp"]
    skill = _bytes(row["source_files"][EXPECTED_SKILL]).decode()
    workflow = _bytes(row["source_files"][".github/workflows/pages.yml"]).decode()
    dashboard = json.loads(_bytes(row["source_files"][".github/spec-dashboard.json"]))
    docs_index = _bytes(row["source_files"]["docs/index.md"]).decode()
    assert "Rapid delivery: the 5-minute contract" in skill
    assert re.search(r"^## Rapid delivery: the 5-minute contract$", skill, re.MULTILINE)
    for term in (
        "mealie_mcp/api_client.py",
        "agent_connector_sdk.cli:serve",
        "MEALIE_BASE_URL",
        "uv run --locked --extra test pytest",
        "Pages",
        "connector: true",
        "render_connector: true",
        "MEALIE_TOKEN",
    ):
        assert term.lower() in skill.lower()
    assert "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main" in workflow
    assert "workflow_dispatch:" in workflow
    assert "content_source: docs" in workflow
    assert "spec_dashboard_enabled: true" in workflow
    assert "spec_dashboard_config: .github/spec-dashboard.json" in workflow
    assert dashboard == {"version": 1, "sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}
    assert "[spec delivery dashboard](spec-delivery/)" in docs_index


def test_release_success_is_never_claimed() -> None:
    evidence = _evidence()
    assert evidence["qualification"]["source_release_success_claimed"] is False
    assert evidence["repos"]["mealie-mcp"]["release"]["evidence_claimed"] is False


def test_fixture_cannot_create_false_json_test_bindings() -> None:
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    assert "mark.spec(" not in fixture_text
    assert "# spec:" not in fixture_text
