"""Source-bound evidence for the R159/R160/R161/R162/R168/R169 leaf train.

The fixture carries immutable consumer source/status bytes and the bodies of
successful exact-source Pages publications. Existing .1/.2 evidence is kept as
baseline metadata; only the exact 13 target leaves are bound by this test.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r159_r169.json"
EXPECTED_PROVIDER = "80dbc06b47dd63a95e9bfe1c2f6b477acc332318"
EXPECTED_PROVIDER_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_PROVIDER_STATUS = "10e5ca05b961037fda6f7a76af934c9c8bd6395508da37e6c54ba80ec7c61fb1"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_MEMBERS = {"spec-standard", "spec-decomposition", "spec-status", "spec-trailers"}
EXPECTED_ROWS = {
    "PIPE-CONNSPEC-R159.3",
    "PIPE-CONNSPEC-R159.4",
    "PIPE-CONNSPEC-R160.2",
    "PIPE-CONNSPEC-R160.3",
    "PIPE-CONNSPEC-R160.4",
    "PIPE-CONNSPEC-R161.3",
    "PIPE-CONNSPEC-R161.4",
    "PIPE-CONNSPEC-R162.3",
    "PIPE-CONNSPEC-R162.4",
    "PIPE-CONNSPEC-R168.3",
    "PIPE-CONNSPEC-R168.4",
    "PIPE-CONNSPEC-R169.3",
    "PIPE-CONNSPEC-R169.4",
}
EXPECTED_HISTORICAL = {
    "salesforce-agent": {"PIPE-CONNSPEC-R159.1", "PIPE-CONNSPEC-R159.2"},
    "scholarx": {"PIPE-CONNSPEC-R160.1"},
    "searxng-mcp": {"PIPE-CONNSPEC-R161.1"},
    "servicenow-api": {"PIPE-CONNSPEC-R162.1", "PIPE-CONNSPEC-R162.2"},
    "tunnel-manager": {"PIPE-CONNSPEC-R168.1", "PIPE-CONNSPEC-R168.2"},
    "twenty-mcp": {"PIPE-CONNSPEC-R169.1", "PIPE-CONNSPEC-R169.2"},
}


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _bytes(document: dict) -> bytes:
    assert document["encoding"] == "base64"
    return base64.b64decode(document["data"], validate=True)


def _rows(evidence: dict) -> dict[str, dict]:
    return {
        requirement_id: {"repo": repo, "data": row}
        for repo, row in evidence["repos"].items()
        for requirement_id, qualified in row["strict_leaves"].items()
        if qualified
    }


@pytest.mark.spec("PIPE-CONNSPEC-R159.3")
@pytest.mark.spec("PIPE-CONNSPEC-R159.4")
@pytest.mark.spec("PIPE-CONNSPEC-R160.2")
@pytest.mark.spec("PIPE-CONNSPEC-R160.3")
@pytest.mark.spec("PIPE-CONNSPEC-R160.4")
@pytest.mark.spec("PIPE-CONNSPEC-R161.3")
@pytest.mark.spec("PIPE-CONNSPEC-R161.4")
@pytest.mark.spec("PIPE-CONNSPEC-R162.3")
@pytest.mark.spec("PIPE-CONNSPEC-R162.4")
@pytest.mark.spec("PIPE-CONNSPEC-R168.3")
@pytest.mark.spec("PIPE-CONNSPEC-R168.4")
@pytest.mark.spec("PIPE-CONNSPEC-R169.3")
@pytest.mark.spec("PIPE-CONNSPEC-R169.4")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    rows = _rows(evidence)
    assert set(rows) == EXPECTED_ROWS
    assert evidence["scope"] == sorted(EXPECTED_ROWS)
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 1, ".3": 6, ".4": 6}
    assert evidence["qualification"] == {
        "already_qualified_dot_one_recounted": False,
        "already_qualified_dot_two_recounted": False,
        "rollups_promoted": False,
        "source_release_success_claimed": False,
        "held_rows_included": [],
        "generic_rows_included": [],
    }
    assert set(evidence["repos"]) == set(EXPECTED_HISTORICAL)
    for requirement_id, row in rows.items():
        source = row["data"]
        assert len(source["sha"]) == 40 and all(char in "0123456789abcdef" for char in source["sha"])
        assert source["sha"] != EXPECTED_PROVIDER
        assert source["strict_leaves"][requirement_id] is True
    for repo, historical in EXPECTED_HISTORICAL.items():
        assert set(evidence["repos"][repo]["historical_verified_leaves"]) == historical


def test_provider_mapping_and_baseline_status_are_immutable() -> None:
    evidence = _evidence()
    provider = evidence["provider"]
    assert provider["requirements_sha256"] == EXPECTED_PROVIDER_REQUIREMENTS
    assert provider["status_sha256"] == EXPECTED_PROVIDER_STATUS
    provider_status = json.loads(_bytes(provider["source_files"]["status.json"]))
    assert (
        hashlib.sha256(_bytes(provider["source_files"]["requirements.md"])).hexdigest()
        == EXPECTED_PROVIDER_REQUIREMENTS
    )
    assert hashlib.sha256(_bytes(provider["source_files"]["status.json"])).hexdigest() == EXPECTED_PROVIDER_STATUS
    assert (
        hashlib.sha256(_bytes(provider["source_files"]["cli.py"])).hexdigest()
        == provider["source_files"]["cli.py"]["sha256"]
    )
    assert (
        hashlib.sha256(_bytes(provider["source_files"]["pre-commit-template.yaml"])).hexdigest()
        == provider["canonical_template"]["sha256"]
    )
    assert provider["spec_group"] == list(GROUPS["spec"])
    assert set(provider["spec_group"]) == EXPECTED_SPEC_MEMBERS
    assert provider["canonical_template"]["rev"] == "main"
    assert set(provider["canonical_template"]["hooks"]) == EXPECTED_HOOKS
    baseline = {row["id"]: row for row in provider_status["requirements"]}
    assert evidence["central_requirements"] == {
        row_id: baseline[row_id] for row_id in sorted(evidence["central_requirements"])
    }
    for requirement_id in EXPECTED_ROWS:
        current = baseline[requirement_id]
        assert current["delivery_state"] == "SPECIFIED"
        assert current["landed_in"] == []
        assert current["verified_by"] == []
    for repo, historical in EXPECTED_HISTORICAL.items():
        for requirement_id in historical:
            current = baseline[requirement_id]
            assert current["delivery_state"] == "VERIFIED"
            assert current["landed_in"]
            assert current["verified_by"]


def test_consumer_source_and_status_snapshots_match_declared_hashes() -> None:
    evidence = _evidence()
    for repo, row in evidence["repos"].items():
        required = {
            ".github/workflows/pages.yml",
            ".pre-commit-config.yaml",
            row["dashboard_config"]
            if "dashboard_config" in row
            else evidence["repos"][repo]["pages"]["with"]["spec_dashboard_config"],
        }
        required.add(
            row["skill_path"]
            if "skill_path" in row
            else next(path for path in row["source_files"] if path.endswith("-development/SKILL.md"))
        )
        assert required <= set(row["source_files"]), repo
        for relative, document in row["source_files"].items():
            content = _bytes(document)
            assert len(content) == document["bytes"], (repo, relative)
            assert hashlib.sha256(content).hexdigest() == document["sha256"], (repo, relative)
        for relative, document in row["status_files"].items():
            content = _bytes(document)
            assert len(content) == document["bytes"], (repo, relative)
            assert hashlib.sha256(content).hexdigest() == document["sha256"], (repo, relative)
            parsed = json.loads(content)
            assert parsed["schema_version"] == 2, (repo, relative)
            if relative != "specs/_template/status.json":
                assert parsed["requirements"], (repo, relative)
        config_path = row["pages"]["with"]["spec_dashboard_config"]
        config = json.loads(_bytes(row["source_files"][config_path]))
        assert config["version"] == 1
        assert config["sources"] == [{"glob": "specs/*/status.json", "kind": "spec"}]
        skill_path = next(path for path in row["source_files"] if path.endswith("-development/SKILL.md"))
        skill = _bytes(row["source_files"][skill_path]).decode()
        assert "Rapid delivery: the 5-minute contract" in skill
        assert len(skill.splitlines()) >= 20
        for term in ("pre-commit", "spec", "test"):
            assert term in skill.lower()


def test_consumer_aggregate_hooks_match_provider_and_use_literal_aggregate() -> None:
    evidence = _evidence()
    provider_hooks = set(evidence["provider"]["canonical_template"]["hooks"])
    for repo, row in evidence["repos"].items():
        precommit = _bytes(row["source_files"][".pre-commit-config.yaml"]).decode()
        pipeline_match = re.search(
            r"- repo: https://github.com/Knuckles-Team/pipelines\n(?P<body>.*?)(?=\n- repo:|\Z)",
            precommit,
            flags=re.DOTALL,
        )
        assert pipeline_match, repo
        body = pipeline_match.group("body")
        assert "rev: main" in body, repo
        actual_hooks = set(re.findall(r"^  - id: ([^\s]+)", body, flags=re.MULTILINE))
        assert actual_hooks == provider_hooks, (repo, actual_hooks)
        assert "- id: spec\n" in body, repo
        assert not any(f"- id: {member}" in body for member in EXPECTED_SPEC_MEMBERS), repo
        assert list(GROUPS["spec"]) == evidence["provider"]["spec_group"]


def test_consumer_pages_are_exact_source_published() -> None:
    evidence = _evidence()
    for repo, row in evidence["repos"].items():
        pages = row["pages"]
        assert pages["strict_ready"] is True
        assert pages["caller_count"] == 1
        assert pages["exact_source_publisher_ready"] is True
        hosted = pages["hosted_run"]
        assert hosted["conclusion"] == "success"
        assert hosted["headSha"] == row["sha"]
        assert hosted["workflowName"] == "Deploy GitHub Pages"
        pages_source = _bytes(row["source_files"][".github/workflows/pages.yml"]).decode()
        assert "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main" in pages_source
        assert "spec_dashboard_enabled: true" in pages_source
        assert f"spec_dashboard_config: {pages['with']['spec_dashboard_config']}" in pages_source
        assert pages["with"]["content_source"] == "docs"
        assert pages["pages_api"]["html_url"] == f"https://knuckles-team.github.io/{repo}/"
        assert pages["index_url"] == f"https://knuckles-team.github.io/{repo}/spec-delivery/"
        assert pages["snapshot_url"] == f"https://knuckles-team.github.io/{repo}/spec-delivery/snapshot.json"
        index = pages["index_http"]
        snapshot = pages["snapshot_http"]
        index_content = _bytes(index["body"])
        snapshot_content = _bytes(snapshot["body"])
        assert index["status"] == 200
        assert snapshot["status"] == 200
        assert hashlib.sha256(index_content).hexdigest() == index["body"]["sha256"]
        assert hashlib.sha256(snapshot_content).hexdigest() == snapshot["body"]["sha256"]
        assert snapshot["revision"] == row["sha"]
        parsed = json.loads(snapshot_content)
        assert parsed["version"] == 1
        assert parsed["repository"] == f"Knuckles-Team/{repo}"
        assert parsed["revision"] == row["sha"]
        assert parsed["records"]
        assert snapshot["record_count"] == len(parsed["records"])


def test_release_success_is_never_claimed() -> None:
    evidence = _evidence()
    assert evidence["qualification"]["source_release_success_claimed"] is False
    assert all(not row["release"]["evidence_claimed"] for row in evidence["repos"].values())


def test_fixture_cannot_create_false_json_test_bindings() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    assert "mark.spec(" not in text
    assert "# spec:" not in text


@pytest.mark.parametrize("failed_gate", GROUPS["spec"])
def test_spec_aggregate_dispatches_every_member_and_propagates_failure(monkeypatch, failed_gate: str) -> None:
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
