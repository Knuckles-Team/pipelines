"""Source-bound proof for the genuinely new R138/R145 Pages and skill leaves.

The pre-existing .1/.2 rows stay historical. This test qualifies only the
merged Pages callers and substantive development skills, with exact source and
hosted Pages snapshots captured in the fixture.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r138_r145.json"
EXPECTED_PROVIDER = "aa8ee4b58c58b1dc3ad3b078aa43fd10ee41e947"
EXPECTED_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_STATUS = "f691f5caf71d40a2e6d72a22631d8e4432b7b8a5121a2c9218d4a1c57f9d6386"
EXPECTED_ROWS = {
    "PIPE-CONNSPEC-R138.3",
    "PIPE-CONNSPEC-R138.4",
    "PIPE-CONNSPEC-R145.3",
    "PIPE-CONNSPEC-R145.4",
}
EXPECTED_HISTORICAL = {
    "PIPE-CONNSPEC-R138.1",
    "PIPE-CONNSPEC-R138.2",
    "PIPE-CONNSPEC-R145.1",
    "PIPE-CONNSPEC-R145.2",
}
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_MEMBERS = {
    "spec-standard",
    "spec-decomposition",
    "spec-status",
    "spec-trailers",
}
EXPECTED_CONSUMERS = {
    "listmonk-api": {
        "merge": "9b30dd390a414e909aef6bd6b7f44ca285382401",
        "pages_run": 40408952369,
        "dashboard": ".github/spec-dashboard.json",
        "skill": "listmonk_api/skills/listmonk-api-development/SKILL.md",
        "repo_url": "https://knuckles-team.github.io/listmonk-api/",
        "records": 7,
        "skill_terms": (
            "connector SDK",
            "LISTMONK_URL",
            "LISTMONK_TOKEN",
            "listmonk_api.mcp_server",
            "uv run --locked --extra test pytest",
            "Pages",
            "uv sync --locked",
            "TLS",
            "action-routed",
        ),
    },
    "objectstore-mcp": {
        "merge": "c2b8582c261a8540149ab07a482218e4005682a9",
        "pages_run": 40408846116,
        "dashboard": ".config/spec-dashboard.json",
        "skill": "objectstore_mcp/skills/objectstore-mcp-development/SKILL.md",
        "repo_url": "https://knuckles-team.github.io/objectstore-mcp/",
        "records": 2,
        "skill_terms": (
            "ObjectStoreBackend",
            "agent-connector-sdk",
            "objects",
            "buckets",
            "transfer",
            "uv run --locked --extra test pytest",
            "Pages",
            "skills/**",
            "ontology/**",
            "action-routed",
        ),
    },
}


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


@pytest.mark.spec("PIPE-CONNSPEC-R138.3")
@pytest.mark.spec("PIPE-CONNSPEC-R138.4")
@pytest.mark.spec("PIPE-CONNSPEC-R145.3")
@pytest.mark.spec("PIPE-CONNSPEC-R145.4")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert set(evidence["repos"]) == set(EXPECTED_CONSUMERS)
    assert set(_qualified(evidence)) == EXPECTED_ROWS
    assert evidence["scope"] == sorted(EXPECTED_ROWS)
    assert evidence["target_rows"] == sorted(EXPECTED_ROWS)
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 0, ".3": 2, ".4": 2}
    assert evidence["qualification"] == {
        "already_qualified_dot_one_recounted": False,
        "already_qualified_dot_two_recounted": False,
        "rollups_promoted": False,
        "source_release_success_claimed": False,
        "held_rows_included": [],
        "generic_rows_included": [],
    }
    for repo, expected in EXPECTED_CONSUMERS.items():
        row = evidence["repos"][repo]
        assert row["sha"] == row["candidate_sha"] == expected["merge"]
        assert set(row["historical_verified_leaves"]) == {
            f"PIPE-CONNSPEC-R{row['row'][1:]}.1",
            f"PIPE-CONNSPEC-R{row['row'][1:]}.2",
        }
        assert not set(row["historical_verified_leaves"]) & EXPECTED_ROWS


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
    for repo, expected in EXPECTED_CONSUMERS.items():
        row = evidence["repos"][repo]
        required = {
            expected["dashboard"],
            ".github/workflows/pages.yml",
            ".pre-commit-config.yaml",
            "docs/index.md",
            expected["skill"],
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


@pytest.mark.spec("PIPE-CONNSPEC-R138.3")
@pytest.mark.spec("PIPE-CONNSPEC-R145.3")
def test_pages_are_exact_merged_source_published() -> None:
    evidence = _evidence()
    for repo, expected in EXPECTED_CONSUMERS.items():
        row = evidence["repos"][repo]
        pages = row["pages"]
        assert pages["strict_ready"] is True
        assert pages["caller_count"] == 1
        assert pages["exact_source_publisher_ready"] is True
        hosted = pages["hosted_run"]
        assert hosted["databaseId"] == expected["pages_run"]
        assert hosted["conclusion"] == "success"
        assert hosted["headSha"] == expected["merge"]
        assert hosted["workflowName"] == "Deploy GitHub Pages"
        assert pages["with"] == {
            "content_source": "docs",
            "spec_dashboard_enabled": True,
            "spec_dashboard_config": expected["dashboard"],
        }
        api = pages["pages_api"]
        assert api["html_url"] == expected["repo_url"]
        assert api["build_type"] == "workflow"
        assert api["public"] is True
        assert api["https_enforced"] is True
        assert api["source"] == {"branch": "main", "path": "/"}
        assert pages["index_url"] == f"{expected['repo_url']}spec-delivery/index.html"
        assert pages["snapshot_url"] == f"{expected['repo_url']}spec-delivery/snapshot.json"
        index_content = _bytes(pages["index.html"]["body"])
        snapshot_content = _bytes(pages["snapshot.json"]["body"])
        assert index_content
        parsed = json.loads(snapshot_content)
        assert pages["snapshot_revision"] == expected["merge"]
        assert pages["snapshot_repository"] == f"Knuckles-Team/{repo}"
        assert pages["snapshot_record_count"] == len(parsed["records"]) == expected["records"]
        assert parsed["revision"] == expected["merge"]
        assert parsed["repository"] == f"Knuckles-Team/{repo}"
        assert parsed["records"]


@pytest.mark.spec("PIPE-CONNSPEC-R138.4")
@pytest.mark.spec("PIPE-CONNSPEC-R145.4")
def test_skill_contract_is_substantive_and_path_bound() -> None:
    evidence = _evidence()
    for repo, expected in EXPECTED_CONSUMERS.items():
        row = evidence["repos"][repo]
        skill = _bytes(row["source_files"][expected["skill"]]).decode()
        workflow = _bytes(row["source_files"][".github/workflows/pages.yml"]).decode()
        dashboard = json.loads(_bytes(row["source_files"][expected["dashboard"]]))
        docs_index = _bytes(row["source_files"]["docs/index.md"]).decode()
        assert "Rapid delivery: the 5-minute contract" in skill
        assert re.search(r"^## Rapid delivery: the 5-minute contract$", skill, re.MULTILINE)
        for term in expected["skill_terms"]:
            assert term.lower() in skill.lower(), (repo, term)
        assert "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main" in workflow
        assert "workflow_dispatch:" in workflow
        assert "content_source: docs" in workflow
        assert "spec_dashboard_enabled: true" in workflow
        assert f"spec_dashboard_config: {expected['dashboard']}" in workflow
        assert dashboard == {"version": 1, "sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}
        assert "spec-delivery/" in docs_index


def test_release_success_is_never_claimed() -> None:
    evidence = _evidence()
    assert evidence["qualification"]["source_release_success_claimed"] is False
    assert all(not row["release"]["evidence_claimed"] for row in evidence["repos"].values())


def test_fixture_cannot_create_false_json_test_bindings() -> None:
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    assert "mark.spec(" not in fixture_text
    assert "# spec:" not in fixture_text
