"""Source-bound proof for the exact R173 consumer adoption leaves.

The fixture captures immutable Wger source bytes, status trees, the canonical
provider mapping, the successful merged-source Pages run, and public Pages
bodies. R173.1 is historical baseline evidence only; this test qualifies
exactly R173.2, R173.3, and R173.4.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r173.json"
EXPECTED_PROVIDER = "7f0f0c0ecf4b6340ae958a04837a81fcd90f92e1"
EXPECTED_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_STATUS = "6be97e9060fdabaa828ce9323172d4d1294f28728ab9f4ea8c97bf7da223dfa0"
EXPECTED_CONSUMER = "e4e46b7a21075fd9600c5797de8a33e55857723d"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_MEMBERS = {"spec-standard", "spec-decomposition", "spec-status", "spec-trailers"}
EXPECTED_ROWS = {
    "PIPE-CONNSPEC-R173.2",
    "PIPE-CONNSPEC-R173.3",
    "PIPE-CONNSPEC-R173.4",
}
EXPECTED_HISTORICAL = {"PIPE-CONNSPEC-R173.1"}


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


@pytest.mark.spec("PIPE-CONNSPEC-R173.2")
@pytest.mark.spec("PIPE-CONNSPEC-R173.3")
@pytest.mark.spec("PIPE-CONNSPEC-R173.4")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert set(evidence["repos"]) == {"wger-agent"}
    assert set(_qualified(evidence)) == EXPECTED_ROWS
    assert evidence["scope"] == sorted(EXPECTED_ROWS)
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 1, ".3": 1, ".4": 1}
    assert evidence["qualification"] == {
        "already_qualified_dot_one_recounted": False,
        "already_qualified_dot_two_recounted": False,
        "rollups_promoted": False,
        "source_release_success_claimed": False,
        "held_rows_included": [],
        "generic_rows_included": [],
        "mcp_artifact_guard_blocked": True,
    }
    for requirement_id, row in _qualified(evidence).items():
        source = row["data"]
        assert len(source["sha"]) == 40 and all(char in "0123456789abcdef" for char in source["sha"])
        assert source["strict_leaves"][requirement_id] is True
        assert source["sha"] == EXPECTED_CONSUMER
    assert evidence["repos"]["wger-agent"]["historical_verified_leaves"] == sorted(EXPECTED_HISTORICAL)
    assert "PIPE-CONNSPEC-R173.1" not in EXPECTED_ROWS


def test_provider_mapping_and_baseline_status_are_immutable() -> None:
    evidence = _evidence()
    provider = evidence["provider"]
    assert provider["requirements_sha256"] == EXPECTED_REQUIREMENTS
    assert provider["status_sha256"] == EXPECTED_STATUS
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
    row = evidence["repos"]["wger-agent"]
    required = {
        ".github/workflows/pages.yml",
        ".pre-commit-config.yaml",
        row["dashboard_config"],
        row["skill_path"],
    }
    assert required <= set(row["source_files"])
    for relative, document in row["source_files"].items():
        _bytes(document)
    for relative, document in row["status_files"].items():
        parsed = json.loads(_bytes(document))
        assert parsed["schema_version"] == 2, relative
        if relative != "specs/_template/status.json":
            assert parsed["requirements"], relative
    config = json.loads(_bytes(row["source_files"][row["dashboard_config"]]))
    assert config == {"version": 1, "sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}
    skill = _bytes(row["source_files"][row["skill_path"]]).decode()
    assert "Rapid delivery: the 5-minute contract" in skill
    for term in ("pre-commit", "spec", "test"):
        assert term in skill.lower()


def test_aggregate_hook_and_pages_source_contracts() -> None:
    evidence = _evidence()
    row = evidence["repos"]["wger-agent"]
    assert row["precommit"]["ready"] is True
    assert row["precommit"]["aggregate_mapping_accepted"] is True
    assert row["precommit"]["aggregate_mapping"] == list(GROUPS["spec"])
    assert row["precommit"]["aggregate_spec_present"] is True
    assert row["precommit"]["missing_template_hooks"] == []
    assert row["precommit"]["validate_config"]["rc"] == 0
    workflow = _bytes(row["source_files"][".github/workflows/pages.yml"]).decode()
    assert "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main" in workflow
    assert "content_source: docs" in workflow
    assert "spec_dashboard_enabled: true" in workflow
    assert f"spec_dashboard_config: {row['dashboard_config']}" in workflow


def test_consumer_pages_are_exact_source_published() -> None:
    evidence = _evidence()
    row = evidence["repos"]["wger-agent"]
    pages = row["pages"]
    assert pages["strict_ready"] is True
    assert pages["caller_count"] == 1
    assert pages["exact_source_publisher_ready"] is True
    hosted = pages["hosted_run"]
    assert hosted["conclusion"] == "success"
    assert hosted["headSha"] == row["sha"] == EXPECTED_CONSUMER
    assert hosted["workflowName"] == "Deploy GitHub Pages"
    assert pages["with"]["content_source"] == "docs"
    assert pages["with"]["spec_dashboard_enabled"] is True
    assert pages["pages_api"]["html_url"] == "https://knuckles-team.github.io/wger-agent/"
    assert pages["index_url"] == "https://knuckles-team.github.io/wger-agent/spec-delivery/index.html"
    assert pages["snapshot_url"] == "https://knuckles-team.github.io/wger-agent/spec-delivery/snapshot.json"
    index = pages["index.html"]
    snapshot = pages["snapshot.json"]
    index_content = _bytes(index["body"])
    snapshot_content = _bytes(snapshot["body"])
    assert index["status"] == 200
    assert snapshot["status"] == 200
    assert pages["snapshot_revision"] == row["sha"]
    assert pages["snapshot_repository"] == "Knuckles-Team/wger-agent"
    parsed = json.loads(snapshot_content)
    assert parsed["version"] == 1
    assert parsed["repository"] == "Knuckles-Team/wger-agent"
    assert parsed["revision"] == row["sha"]
    assert parsed["records"]
    assert pages["snapshot_record_count"] == len(parsed["records"])
    assert index_content


def test_release_success_is_never_claimed() -> None:
    evidence = _evidence()
    assert evidence["qualification"]["source_release_success_claimed"] is False
    assert evidence["qualification"]["mcp_artifact_guard_blocked"] is True
    assert all(not row.get("release", {}).get("evidence_claimed", False) for row in evidence["repos"].values())


def test_fixture_cannot_create_false_json_test_bindings() -> None:
    assert "mark.spec(" not in FIXTURE.read_text(encoding="utf-8")
    assert "# spec:" not in FIXTURE.read_text(encoding="utf-8")
