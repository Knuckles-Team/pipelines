"""Source-bound proof for the OpenBao R148.4 development-skill leaf.

R148.1, R148.2, and R148.3 are historical verified evidence at the provider
baseline. This test qualifies only R148.4 and binds the skill to the exact
merged source and the supplied publication receipt.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r148.json"
EXPECTED_PROVIDER = "3dae20078dcbd8f867302708f05d8b5621c7cf49"
EXPECTED_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_STATUS = "5135cf57eff6c1e120b60c64659ffe596b17de0fceb471c9d614d9d3c0120729"
EXPECTED_CONSUMER = "4e8340e0733ffa6b82e6d28df5e0921d7a444acb"
EXPECTED_ROWS = {"PIPE-CONNSPEC-R148.4"}
EXPECTED_HISTORICAL = {
    "PIPE-CONNSPEC-R148.1",
    "PIPE-CONNSPEC-R148.2",
    "PIPE-CONNSPEC-R148.3",
}
EXPECTED_PROVIDER_PATHS = {
    "cli.py": "pipelines_hooks/cli.py",
    "pre-commit-template.yaml": "templates/connector/pre-commit-config.yaml",
    "requirements.md": "specs/connector-spec-delivery/requirements.md",
    "status.json": "specs/connector-spec-delivery/status.json",
}
EXPECTED_SKILL = "openbao_mcp/skills/openbao-mcp-development/SKILL.md"
EXPECTED_STATUS_PATHS = {
    "specs/_template/status.json",
    "specs/connector-content/status.json",
    "specs/governed-http/status.json",
}
EXPECTED_RECEIPT_SHA = "95cbf009f130919575fd85de323c60f5681555a9831e5e2d9abea5e21a5d5af2"
EXPECTED_WHEEL_SHA = "cb12dd245c99894e888b2cd8b8c57ac9cfd7194599650f8663400e0286d72496"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_MEMBERS = {"spec-standard", "spec-decomposition", "spec-status", "spec-trailers"}


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


@pytest.mark.spec("PIPE-CONNSPEC-R148.4")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert set(evidence["repos"]) == {"openbao-mcp"}
    assert set(_qualified(evidence)) == EXPECTED_ROWS
    assert evidence["scope"] == sorted(EXPECTED_ROWS)
    assert evidence["target_rows"] == sorted(EXPECTED_ROWS)
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
    row = evidence["repos"]["openbao-mcp"]
    assert row["row"] == "R148"
    assert row["sha"] == row["candidate_sha"] == EXPECTED_CONSUMER
    assert set(row["historical_verified_leaves"]) == EXPECTED_HISTORICAL
    assert not EXPECTED_HISTORICAL & EXPECTED_ROWS
    assert row["strict_leaves"] == {
        "PIPE-CONNSPEC-R148.1": False,
        "PIPE-CONNSPEC-R148.2": False,
        "PIPE-CONNSPEC-R148.3": False,
        "PIPE-CONNSPEC-R148.4": True,
    }


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
    assert set(provider["canonical_template"]["hooks"]) == EXPECTED_HOOKS
    assert provider["spec_group"]["aggregate_mapping_accepted"] is True
    assert provider["spec_group"]["aggregate_mapping_proven"] is True
    assert provider["spec_group"]["members"] == list(GROUPS["spec"])
    assert set(provider["spec_group"]["members"]) == EXPECTED_SPEC_MEMBERS
    baseline = {row["id"]: row for row in provider_status["requirements"]}
    assert evidence["central_requirements"] == {
        row_id: baseline[row_id] for row_id in sorted(evidence["central_requirements"])
    }
    assert baseline["PIPE-CONNSPEC-R148"]["delivery_state"] == "SPECIFIED"
    assert baseline["PIPE-CONNSPEC-R148"]["landed_in"] == []
    assert baseline["PIPE-CONNSPEC-R148"]["verified_by"] == []
    current = baseline["PIPE-CONNSPEC-R148.4"]
    assert current["delivery_state"] == "SPECIFIED"
    assert current["landed_in"] == []
    assert current["verified_by"] == []
    for requirement_id in EXPECTED_HISTORICAL:
        current = baseline[requirement_id]
        assert current["delivery_state"] == "VERIFIED"
        assert current["landed_in"]
        assert current["verified_by"]


def test_consumer_skill_and_status_snapshots_match_declared_hashes() -> None:
    row = _evidence()["repos"]["openbao-mcp"]
    assert row["skill_path"] == EXPECTED_SKILL
    assert row["source_paths"] == {EXPECTED_SKILL: EXPECTED_SKILL}
    assert set(row["source_files"]) == {EXPECTED_SKILL}
    assert row["status_paths"] == {path: path for path in EXPECTED_STATUS_PATHS}
    assert set(row["status_files"]) == EXPECTED_STATUS_PATHS
    for document in row["source_files"].values():
        _bytes(document)
    for relative, document in row["status_files"].items():
        parsed = json.loads(_bytes(document))
        assert parsed["schema_version"] == 2, relative
        if relative != "specs/_template/status.json":
            assert parsed["requirements"], relative


@pytest.mark.spec("PIPE-CONNSPEC-R148.4")
def test_skill_contract_is_substantive_and_path_bound() -> None:
    row = _evidence()["repos"]["openbao-mcp"]
    skill = _bytes(row["source_files"][EXPECTED_SKILL]).decode()
    assert re.search(r"^## Rapid delivery: the 5-minute contract$", skill, re.MULTILINE)
    for term in row["skill_terms"]:
        assert term.lower() in skill.lower(), term
    assert "openbao-agent" not in skill
    assert "OPENBAO_TOKEN =" not in skill


def test_publication_receipt_is_exact_without_promoting_other_rows() -> None:
    evidence = _evidence()
    row = evidence["repos"]["openbao-mcp"]
    publication = row["publication"]
    assert publication == {
        "source_sha": EXPECTED_CONSUMER,
        "pages_run": 40424771870,
        "pages_conclusion": "success",
        "package_run": 40424771404,
        "package_conclusion": "success",
        "version": "2.3.5",
        "wheel_sha256": EXPECTED_WHEEL_SHA,
        "wheel_contains_skill": True,
        "sdist_contains_skill": True,
    }
    assert row["receipt"]["sha256"] == EXPECTED_RECEIPT_SHA
    assert evidence["qualification"]["source_release_success_claimed"] is False
    assert evidence["qualification"]["rollups_promoted"] is False


def test_fixture_cannot_create_false_json_test_bindings() -> None:
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    assert "mark.spec(" not in fixture_text
    assert "# spec:" not in fixture_text
