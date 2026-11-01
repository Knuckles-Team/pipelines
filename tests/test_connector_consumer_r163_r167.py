"""Source-bound central evidence for the R158/R163/R164/R165/R167 leaf train.

The fixture stores immutable consumer source/status bytes and exact-source Pages
responses. Only the eleven strict .2/.3/.4 leaves are qualified here; prior .1 rows
are baseline evidence and held R166 rows are intentionally absent.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r163_r167.json"
EXPECTED_PROVIDER = "490076d94f465da0f9396f69d5f4193bd8c20d8c"
EXPECTED_PROVIDER_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_PROVIDER_STATUS = "fe61582cdd4b9cb6872094f9dc03a8160bc8009907422377608bc0c0719da0cb"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_MEMBERS = {"spec-standard", "plan-conformance", "spec-decomposition", "spec-status", "spec-trailers"}
EXPECTED_ROWS = {
    "PIPE-CONNSPEC-R158.2",
    "PIPE-CONNSPEC-R158.3",
    "PIPE-CONNSPEC-R158.4",
    "PIPE-CONNSPEC-R163.3",
    "PIPE-CONNSPEC-R163.4",
    "PIPE-CONNSPEC-R164.3",
    "PIPE-CONNSPEC-R164.4",
    "PIPE-CONNSPEC-R165.3",
    "PIPE-CONNSPEC-R165.4",
    "PIPE-CONNSPEC-R167.3",
    "PIPE-CONNSPEC-R167.4",
}
EXPECTED_HISTORICAL = {
    "rom-manager": {"PIPE-CONNSPEC-R158.1"},
    "spark-mcp": {"PIPE-CONNSPEC-R163.1", "PIPE-CONNSPEC-R163.2"},
    "sql-mcp": {"PIPE-CONNSPEC-R164.1", "PIPE-CONNSPEC-R164.2"},
    "stirlingpdf-agent": {"PIPE-CONNSPEC-R165.1", "PIPE-CONNSPEC-R165.2"},
    "technitium-dns-mcp": {"PIPE-CONNSPEC-R167.1", "PIPE-CONNSPEC-R167.2"},
}


def _evidence() -> dict:
    evidence = json.loads(FIXTURE.read_text(encoding="utf-8"))
    repos: dict[str, dict] = {}
    for repo, descriptor in evidence["repo_shards"].items():
        shard_path = FIXTURE.parent / descriptor["path"]
        shard_bytes = shard_path.read_bytes()
        assert hashlib.sha256(shard_bytes).hexdigest() == descriptor["sha256"]
        shard = json.loads(shard_bytes)
        assert set(shard) == {repo}
        repos.update(shard)
    evidence["repos"] = repos
    return evidence


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


@pytest.mark.spec("PIPE-CONNSPEC-R158.2")
@pytest.mark.spec("PIPE-CONNSPEC-R158.3")
@pytest.mark.spec("PIPE-CONNSPEC-R158.4")
@pytest.mark.spec("PIPE-CONNSPEC-R163.3")
@pytest.mark.spec("PIPE-CONNSPEC-R163.4")
@pytest.mark.spec("PIPE-CONNSPEC-R164.3")
@pytest.mark.spec("PIPE-CONNSPEC-R164.4")
@pytest.mark.spec("PIPE-CONNSPEC-R165.3")
@pytest.mark.spec("PIPE-CONNSPEC-R165.4")
@pytest.mark.spec("PIPE-CONNSPEC-R167.3")
@pytest.mark.spec("PIPE-CONNSPEC-R167.4")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    rows = _rows(evidence)
    assert set(rows) == EXPECTED_ROWS
    assert evidence["scope"] == sorted(EXPECTED_ROWS)
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 0, ".3": 5, ".4": 5}
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
            row["dashboard_config"],
            row["skill_path"],
        }
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
        config = json.loads(_bytes(row["source_files"][row["dashboard_config"]]))
        assert config == {"version": 1, "sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}
        skill = _bytes(row["source_files"][row["skill_path"]]).decode()
        assert "Rapid delivery: the 5-minute contract" in skill
        assert len(skill.splitlines()) >= 20
        for term in ("pre-commit", "spec", "test"):
            assert term in skill.lower()


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
        index = pages["index.html"]
        snapshot = pages["snapshot.json"]
        index_content = _bytes(index["body"])
        snapshot_content = _bytes(snapshot["body"])
        assert index["status"] == 200
        assert snapshot["status"] == 200
        assert hashlib.sha256(index_content).hexdigest() == index["body"]["sha256"]
        assert hashlib.sha256(snapshot_content).hexdigest() == snapshot["body"]["sha256"]
        assert pages["snapshot_revision"] == row["sha"]
        parsed = json.loads(snapshot_content)
        assert parsed["version"] == 1
        assert parsed["repository"] == f"Knuckles-Team/{repo}"
        assert parsed["revision"] == row["sha"]
        assert parsed["records"]
        assert pages["snapshot_record_count"] == len(parsed["records"])


def test_release_success_is_never_claimed() -> None:
    evidence = _evidence()
    assert evidence["qualification"]["source_release_success_claimed"] is False
    assert all(not row.get("release", {}).get("evidence_claimed", False) for row in evidence["repos"].values())


def test_fixture_cannot_create_false_json_test_bindings() -> None:
    evidence = json.loads(FIXTURE.read_text(encoding="utf-8"))
    paths = [FIXTURE, *[FIXTURE.parent / item["path"] for item in evidence["repo_shards"].values()]]
    for path in paths:
        text = path.read_text(encoding="utf-8")
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
