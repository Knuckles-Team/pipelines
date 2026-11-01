"""Source-bound evidence for the R108/R112/R113/R114/R115 leaf train.

The fixture contains immutable consumer source/status bytes, canonical hook
mapping, and successful exact-source Pages proof. Existing verified .1/.2
rows are retained as baseline evidence and are never recounted as new leaves.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r108_r115.json"
EXPECTED_PROVIDER = "2a048eaad63c8f977ce46312d5228abad8c794f5"
EXPECTED_PROVIDER_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_PROVIDER_STATUS = "1da442d782dec3f9a48146ba80027dd7e71c943d1bdfe4ead69e561f64b3b442"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_LEAVES = {"spec-standard", "plan-conformance", "spec-decomposition", "spec-status", "spec-trailers"}
EXPECTED_ROWS = {
    "PIPE-CONNSPEC-R108.3",
    "PIPE-CONNSPEC-R108.4",
    "PIPE-CONNSPEC-R112.3",
    "PIPE-CONNSPEC-R112.4",
    "PIPE-CONNSPEC-R113.2",
    "PIPE-CONNSPEC-R113.3",
    "PIPE-CONNSPEC-R113.4",
    "PIPE-CONNSPEC-R114.3",
    "PIPE-CONNSPEC-R114.4",
    "PIPE-CONNSPEC-R115.3",
    "PIPE-CONNSPEC-R115.4",
}
EXPECTED_SOURCE_SHAS = {
    "audiobookshelf-mcp": "28f426777c2c7fa4ba07bf78b377608285e990aa",
    "clarity-api": "797073611faf61be84858a414745a1ac1e45cff1",
    "container-manager-mcp": "261689cb22ff40fc7e8dfb4ddabeea781de46df8",
    "data-science-mcp": "f03b94f79f4097d8153997311547a52ff9cca1e9",
    "dockerhub-api": "3bfb7b0471e8fab2d567641a1022d5b8ccf51c36",
}
EXPECTED_HISTORICAL = {
    "audiobookshelf-mcp": {"PIPE-CONNSPEC-R108.1", "PIPE-CONNSPEC-R108.2"},
    "clarity-api": {"PIPE-CONNSPEC-R112.1", "PIPE-CONNSPEC-R112.2"},
    "container-manager-mcp": {"PIPE-CONNSPEC-R113.1"},
    "data-science-mcp": {"PIPE-CONNSPEC-R114.1", "PIPE-CONNSPEC-R114.2"},
    "dockerhub-api": {"PIPE-CONNSPEC-R115.1", "PIPE-CONNSPEC-R115.2"},
}


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _source_bytes(source: dict) -> bytes:
    assert source["encoding"] == "base64"
    return base64.b64decode(source["data"], validate=True)


def _rows(evidence: dict) -> dict[str, dict]:
    return {
        requirement_id: {"repo": repo, "data": repo_row}
        for repo, repo_row in evidence["repos"].items()
        for requirement_id, qualified in repo_row["strict_leaves"].items()
        if qualified
    }


@pytest.mark.spec("PIPE-CONNSPEC-R108.3")
@pytest.mark.spec("PIPE-CONNSPEC-R108.4")
@pytest.mark.spec("PIPE-CONNSPEC-R112.3")
@pytest.mark.spec("PIPE-CONNSPEC-R112.4")
@pytest.mark.spec("PIPE-CONNSPEC-R113.2")
@pytest.mark.spec("PIPE-CONNSPEC-R113.3")
@pytest.mark.spec("PIPE-CONNSPEC-R113.4")
@pytest.mark.spec("PIPE-CONNSPEC-R114.3")
@pytest.mark.spec("PIPE-CONNSPEC-R114.4")
@pytest.mark.spec("PIPE-CONNSPEC-R115.3")
@pytest.mark.spec("PIPE-CONNSPEC-R115.4")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert set(evidence["repos"]) == set(EXPECTED_SOURCE_SHAS)
    rows = _rows(evidence)
    assert set(rows) == EXPECTED_ROWS
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 1, ".3": 5, ".4": 5}
    assert evidence["qualification"]["already_qualified_dot_one_recounted"] is False
    assert evidence["qualification"]["already_qualified_dot_two_recounted"] is False
    assert evidence["qualification"]["rollups_promoted"] is False
    for repo, expected_sha in EXPECTED_SOURCE_SHAS.items():
        row = evidence["repos"][repo]
        assert row["sha"] == expected_sha
        assert len(row["sha"]) == 40 and all(char in "0123456789abcdef" for char in row["sha"])
        assert row["sha"] != evidence["provider"]["sha"]
        assert set(row["historical_verified_leaves"]) == EXPECTED_HISTORICAL[repo]
        for requirement_id in EXPECTED_HISTORICAL[repo]:
            assert row["strict_leaves"][requirement_id] is False


def test_provider_mapping_and_baseline_status_are_immutable() -> None:
    evidence = _evidence()
    provider = evidence["provider"]
    assert provider["requirements_sha256"] == EXPECTED_PROVIDER_REQUIREMENTS
    assert provider["status_sha256"] == EXPECTED_PROVIDER_STATUS
    assert provider["spec_group"] == list(GROUPS["spec"])
    assert set(provider["spec_group"]) == EXPECTED_SPEC_LEAVES
    assert provider["canonical_template"]["rev"] == "main"
    assert set(provider["canonical_template"]["hooks"]) == EXPECTED_HOOKS
    target_rows = set(evidence["target_rows"])
    for parent, entries in evidence["central_requirements"].items():
        parent_id = f"PIPE-CONNSPEC-{parent}"
        assert entries[parent_id]["delivery_state"] == "SPECIFIED"
        assert entries[parent_id]["landed_in"] == []
        assert entries[parent_id]["verified_by"] == []
        for requirement_id, current in entries.items():
            if requirement_id == parent_id:
                continue
            if requirement_id in target_rows:
                assert current["delivery_state"] == "SPECIFIED"
                assert current["landed_in"] == []
                assert current["verified_by"] == []
            elif (
                requirement_id
                in EXPECTED_HISTORICAL[
                    next(
                        repo
                        for repo in evidence["repos"]
                        if requirement_id in evidence["repos"][repo]["historical_verified_leaves"]
                    )
                ]
            ):
                assert current["delivery_state"] == "VERIFIED"
                assert current["landed_in"]
                assert current["verified_by"]


def test_consumer_source_and_status_snapshots_match_declared_hashes() -> None:
    evidence = _evidence()
    required = {".github/workflows/pages.yml", ".pre-commit-config.yaml"}
    for repo, row in evidence["repos"].items():
        source_files = row["source_files"]
        assert required <= set(source_files)
        assert row["dashboard_config"] in source_files
        assert row["skill_path"] in source_files
        for relative, source in source_files.items():
            content = _source_bytes(source)
            assert len(content) == source["bytes"], (repo, relative)
            assert hashlib.sha256(content).hexdigest() == source["sha256"], (repo, relative)
        for relative, source in row["status_files"].items():
            content = _source_bytes(source)
            assert len(content) == source["bytes"], (repo, relative)
            assert hashlib.sha256(content).hexdigest() == source["sha256"], (repo, relative)
            parsed = json.loads(content)
            assert parsed["schema_version"] == 2
            if relative != "specs/_template/status.json":
                assert parsed["requirements"]
        config = json.loads(_source_bytes(source_files[row["dashboard_config"]]))
        assert config["version"] == 1
        assert config["sources"] == [{"glob": "specs/*/status.json", "kind": "spec"}]
        pages = _source_bytes(source_files[".github/workflows/pages.yml"]).decode()
        assert "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main" in pages
        assert "spec_dashboard_enabled: true" in pages
        assert f"spec_dashboard_config: {row['dashboard_config']}" in pages
        precommit = _source_bytes(source_files[".pre-commit-config.yaml"]).decode()
        assert "rev: main" in precommit
        for hook in EXPECTED_HOOKS:
            assert f"- id: {hook}" in precommit
        skill = _source_bytes(source_files[row["skill_path"]]).decode()
        assert "Rapid delivery: the 5-minute contract" in skill
        assert len(skill.splitlines()) >= 25
        for term in ("pre-commit", "spec", "test"):
            assert term.lower() in skill.lower()


def test_consumer_aggregate_hooks_match_provider_and_use_literal_aggregate() -> None:
    evidence = _evidence()
    for repo, row in evidence["repos"].items():
        hooks = row["precommit"]
        assert hooks["aggregate_ready"] is True, repo
        assert hooks["provider"] is True, repo
        assert hooks["canonical_hooks"]["rev"] == evidence["provider"]["canonical_template"]["rev"], repo
        assert set(hooks["canonical_hooks"]["hooks"]) == EXPECTED_HOOKS, repo
        assert set(hooks["hooks"]) == EXPECTED_HOOKS, repo
        assert hooks["literal_hooks_present"] == [], repo
        assert hooks["missing"] == [], repo
        assert hooks["validate_config"]["returncode"] == 0, repo


def test_consumer_pages_are_exact_source_published() -> None:
    evidence = _evidence()
    for repo, row in evidence["repos"].items():
        pages = row["pages"]
        assert pages["strict_ready"] is True, repo
        assert pages["caller_count"] == 1, repo
        assert pages["required_paths"] is True, repo
        assert pages["shape_ready"] is True, repo
        assert pages["exact_source_publisher_ready"] is True, repo
        assert pages["hosted_run"]["conclusion"] == "success", repo
        assert pages["hosted_run"]["headSha"] == row["sha"], repo
        assert pages["with"]["content_source"] == "docs", repo
        assert pages["with"]["spec_dashboard_enabled"] is True, repo
        assert pages["config"]["version"] == 1, repo
        assert pages["http_200"]["status"] == 200, repo
        assert pages["http_200"]["snapshot_revision"] == row["sha"], repo
        assert pages["http_200"]["index_sha256"], repo
        assert pages["http_200"]["snapshot_sha256"], repo
        assert pages["pages_api"]["html_url"] == f"https://knuckles-team.github.io/{repo}/", repo
        assert pages["snapshot_url"].startswith(f"https://knuckles-team.github.io/{repo}/spec-delivery/"), repo


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
