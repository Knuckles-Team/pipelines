"""Source-bound proof for the genuinely new ArchiMate R102.4 leaf.

R102.1, R102.2, and R102.3 are historical verified evidence at the provider
baseline. This test qualifies only the final development-skill leaf and binds it
to the exact final archimate-mcp main commit.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r102.json"
EXPECTED_PROVIDER = "3b62e92a7f574944f91adc0c4312154f9ca3dcb5"
EXPECTED_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_STATUS = "cbd78b3ecfdb3b93b8b87c94d7de2d2defaf67d4c6b3a7e5ef3474d0b15a8208"
EXPECTED_CONSUMER = "ae40d92ecab999afc1867b3426f2c81cd8b7007c"
EXPECTED_ROWS = {"PIPE-CONNSPEC-R102.4"}
EXPECTED_HISTORICAL = {
    "PIPE-CONNSPEC-R102.1",
    "PIPE-CONNSPEC-R102.2",
    "PIPE-CONNSPEC-R102.3",
}
EXPECTED_SKILL = "archimate_mcp/skills/archimate-mcp-development/SKILL.md"
EXPECTED_PROVIDER_PATHS = {
    "cli.py": "pipelines_hooks/cli.py",
    "pre-commit-template.yaml": "templates/connector/pre-commit-config.yaml",
    "requirements.md": "specs/connector-spec-delivery/requirements.md",
    "status.json": "specs/connector-spec-delivery/status.json",
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


@pytest.mark.spec("PIPE-CONNSPEC-R102.4")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert set(evidence["repos"]) == {"archimate-mcp"}
    assert set(_qualified(evidence)) == EXPECTED_ROWS
    assert evidence["scope"] == sorted(EXPECTED_ROWS)
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 0, ".3": 0, ".4": 1}
    assert evidence["qualification"] == {
        "already_qualified_dot_one_recounted": False,
        "already_qualified_dot_two_recounted": False,
        "already_qualified_dot_three_recounted": False,
        "rollups_promoted": False,
        "source_release_success_claimed": False,
        "held_rows_included": [],
        "generic_rows_included": [],
    }
    row = evidence["repos"]["archimate-mcp"]
    assert row["sha"] == row["candidate_sha"] == EXPECTED_CONSUMER
    assert set(row["historical_verified_leaves"]) == EXPECTED_HISTORICAL
    assert not EXPECTED_HISTORICAL & EXPECTED_ROWS


def test_provider_mapping_and_baseline_status_are_immutable() -> None:
    evidence = _evidence()
    provider = evidence["provider"]
    assert provider["requirements_sha256"] == EXPECTED_REQUIREMENTS
    assert provider["status_sha256"] == EXPECTED_STATUS
    assert provider["source_paths"] == EXPECTED_PROVIDER_PATHS
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
    assert set(provider["canonical_template"]["hooks"]) == {
        "connector-standard",
        "dependency-readiness",
        "secrets",
        "spec",
        "tests-fast",
    }
    assert provider["spec_group"]["aggregate_mapping_accepted"] is True
    assert provider["spec_group"]["aggregate_mapping_proven"] is True
    assert provider["spec_group"]["members"] == list(GROUPS["spec"])
    assert set(provider["spec_group"]["members"]) == {
        "spec-standard",
        "plan-conformance",
        "spec-decomposition",
        "spec-status",
        "spec-trailers",
    }
    baseline = {row["id"]: row for row in provider_status["requirements"]}
    assert evidence["central_requirements"] == {
        row_id: baseline[row_id] for row_id in sorted(evidence["central_requirements"])
    }
    assert baseline["PIPE-CONNSPEC-R102.4"]["delivery_state"] == "SPECIFIED"
    assert baseline["PIPE-CONNSPEC-R102.4"]["landed_in"] == []
    assert baseline["PIPE-CONNSPEC-R102.4"]["verified_by"] == []
    for requirement_id in EXPECTED_HISTORICAL:
        current = baseline[requirement_id]
        assert current["delivery_state"] == "VERIFIED"
        assert current["landed_in"]
        assert current["verified_by"]


def test_consumer_skill_and_status_snapshots_match_declared_hashes() -> None:
    evidence = _evidence()
    row = evidence["repos"]["archimate-mcp"]
    assert row["source_paths"] == {EXPECTED_SKILL: EXPECTED_SKILL}
    assert row["status_paths"] == {path: path for path in row["status_files"]}
    assert set(row["source_files"]) == {EXPECTED_SKILL}
    assert set(row["status_files"]) == {
        "specs/_template/status.json",
        "specs/connector-content/status.json",
    }
    for document in row["source_files"].values():
        _bytes(document)
    for relative, document in row["status_files"].items():
        parsed = json.loads(_bytes(document))
        assert parsed["schema_version"] == 2
        if relative != "specs/_template/status.json":
            assert parsed["requirements"]


@pytest.mark.spec("PIPE-CONNSPEC-R102.4")
def test_skill_contract_is_substantive_and_path_bound() -> None:
    skill = _bytes(_evidence()["repos"]["archimate-mcp"]["source_files"][EXPECTED_SKILL]).decode()
    assert "Rapid delivery: the 5-minute contract" in skill
    assert "archimate_mcp/api/" in skill
    assert "agent_connector_sdk.cli:serve" in skill
    assert "ARCHI_MODEL_PATH" in skill
    for term in ("uv run pytest", "Pages", "native builds"):
        assert term.lower() in skill.lower()
    assert re.search(r"^## Rapid delivery: the 5-minute contract$", skill, re.MULTILINE)


def test_release_success_is_never_claimed() -> None:
    evidence = _evidence()
    assert evidence["qualification"]["source_release_success_claimed"] is False


def test_fixture_cannot_create_false_json_test_bindings() -> None:
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    assert "mark.spec(" not in fixture_text
    assert "# spec:" not in fixture_text
