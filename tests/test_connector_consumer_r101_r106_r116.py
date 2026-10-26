"""Immutable source-bound proof for the strict R101/R106/R116 leaf train.

The fixture records exact consumer commits after provider PR #296, source-file
fingerprints, aggregate-hook results, and successful hosted Pages evidence. The
tests validate that evidence without invoking consumer code or making network
requests. Already verified ``.1`` rows remain historical and are not recounted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r101_r106_r116.json"
EXPECTED_PROVIDER = "2a048eaad63c8f977ce46312d5228abad8c794f5"
EXPECTED_PROVIDER_REQUIREMENTS = "2cb6e004ecfbbc7594e276e20266204074b6de68187985fe9e152f756004cca8"
EXPECTED_PROVIDER_STATUS = "389e682ee0b1647aa5e724e59fff8735ee1bd2156fc75397f2df515ff99d87f1"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_LEAVES = {"spec-standard", "spec-decomposition", "spec-status", "spec-trailers"}
EXPECTED_SOURCE_SHAS = {
    "ansible-tower-mcp": "2df4b183d7219074c1dbd95ddbbc9d7bdc18bf7e",
    "atlassian-agent": "55a2e5692fe7da9b2947d96f88112039bd93cf55",
    "documentdb-mcp": "73385f9c3346722a67940f3393ca02c74bef3a86",
}
EXPECTED_ROWS = {
    "PIPE-CONNSPEC-R101.2",
    "PIPE-CONNSPEC-R101.3",
    "PIPE-CONNSPEC-R101.4",
    "PIPE-CONNSPEC-R106.2",
    "PIPE-CONNSPEC-R106.3",
    "PIPE-CONNSPEC-R106.4",
    "PIPE-CONNSPEC-R116.2",
    "PIPE-CONNSPEC-R116.3",
}


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _rows(evidence: dict) -> dict[str, dict]:
    return {
        f"PIPE-CONNSPEC-{repo_row['row'].split('-')[-1]}.{suffix}": {
            "repo": repo,
            "data": repo_row,
        }
        for repo, repo_row in evidence["repos"].items()
        for suffix in ("2", "3", "4")
        if repo_row["strict_leaves"].get(f"{repo_row['row']}.{suffix}")
    }


@pytest.mark.spec("PIPE-CONNSPEC-R101.2")
@pytest.mark.spec("PIPE-CONNSPEC-R101.3")
@pytest.mark.spec("PIPE-CONNSPEC-R101.4")
@pytest.mark.spec("PIPE-CONNSPEC-R106.2")
@pytest.mark.spec("PIPE-CONNSPEC-R106.3")
@pytest.mark.spec("PIPE-CONNSPEC-R106.4")
@pytest.mark.spec("PIPE-CONNSPEC-R116.2")
@pytest.mark.spec("PIPE-CONNSPEC-R116.3")
def test_strict_leaf_set_is_exact_and_source_bound() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert set(evidence["repos"]) == set(EXPECTED_SOURCE_SHAS)
    rows = _rows(evidence)
    assert set(rows) == EXPECTED_ROWS
    for repo, expected_sha in EXPECTED_SOURCE_SHAS.items():
        row = evidence["repos"][repo]
        assert row["sha"] == expected_sha
        assert len(row["sha"]) == 40 and all(char in "0123456789abcdef" for char in row["sha"])
        assert row["sha"] != evidence["provider"]["sha"]
        assert row["historical_verified_leaves"] == [f"{row['row']}.1"]
        assert row["strict_leaves"][f"{row['row']}.1"] is False
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 3, ".3": 3, ".4": 2}
    assert evidence["qualification"]["already_qualified_dot_one_recounted"] is False
    assert evidence["qualification"]["rollups_promoted"] is False


def test_provider_mapping_and_baseline_status_are_immutable() -> None:
    evidence = _evidence()
    provider = evidence["provider"]
    assert provider["requirements_sha256"] == EXPECTED_PROVIDER_REQUIREMENTS
    assert provider["status_sha256"] == EXPECTED_PROVIDER_STATUS
    assert provider["spec_group"] == list(GROUPS["spec"])
    assert set(provider["spec_group"]) == EXPECTED_SPEC_LEAVES
    assert provider["canonical_template"]["rev"] == "main"
    assert set(provider["canonical_template"]["hooks"]) == EXPECTED_HOOKS
    for parent, entries in evidence["central_requirements"].items():
        assert entries[f"PIPE-CONNSPEC-{parent}"]["delivery_state"] == "SPECIFIED"
        assert entries[f"PIPE-CONNSPEC-{parent}"]["landed_in"] == []
        assert entries[f"PIPE-CONNSPEC-{parent}"]["verified_by"] == []
        historical = entries[f"PIPE-CONNSPEC-{parent}.1"]
        assert historical["delivery_state"] == "VERIFIED"
        assert historical["landed_in"]
        assert historical["verified_by"]
        for suffix in (".2", ".3", ".4"):
            current = entries[f"PIPE-CONNSPEC-{parent}{suffix}"]
            assert current["delivery_state"] == "SPECIFIED"
            assert current["landed_in"] == []
            assert current["verified_by"] == []


def test_consumer_source_snapshots_match_their_declared_hashes() -> None:
    evidence = _evidence()
    required = {".github/spec-dashboard.json", ".github/workflows/pages.yml", ".pre-commit-config.yaml"}
    for repo, row in evidence["repos"].items():
        source_files = row["source_files"]
        assert required <= set(source_files)
        for relative, source in source_files.items():
            content = source["content"].encode()
            assert len(content) == source["bytes"], (repo, relative)
            assert hashlib.sha256(content).hexdigest() == source["sha256"], (repo, relative)
        if repo != "documentdb-mcp":
            matches = row["skills"]["rapid_delivery_matches"]
            assert len(matches) == 1
            skill = source_files[matches[0]]
            assert row["skills"]["ready"] is True
            assert row["skills"]["required_phrase"] in skill["content"]
            assert "## Setup and gates" in skill["content"]
            assert "## Delivery discipline" in skill["content"]
            assert len(skill["content"].splitlines()) >= 40
        else:
            assert row["skills"] == {
                "rapid_delivery_matches": [],
                "required_phrase": None,
                "ready": False,
            }
            assert row["strict_leaves"]["PIPE-CONNSPEC-R116.4"] is False


def test_consumer_aggregate_hooks_match_provider_and_validate() -> None:
    evidence = _evidence()
    provider = evidence["provider"]
    for repo, row in evidence["repos"].items():
        hooks = row["precommit"]
        assert hooks["aggregate_ready"] is True, repo
        assert hooks["provider"] is True, repo
        assert hooks["canonical_hooks"]["rev"] == provider["canonical_template"]["rev"], repo
        assert set(hooks["canonical_hooks"]["hooks"]) == set(provider["canonical_template"]["hooks"]), repo
        assert set(hooks["hooks"]) == EXPECTED_HOOKS, repo
        # The consumer configs intentionally use the canonical aggregate
        # ``spec`` hook. The literal source hooks are provider-side members,
        # not copied into each consumer configuration.
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
        assert pages["http_200_ready"] is True, repo
        assert pages["live_http"]["status"] == 200, repo
        assert pages["live_http"]["sha256"], repo
        assert pages["live_http"]["url"].startswith(f"https://knuckles-team.github.io/{repo}/spec-delivery/"), repo
        assert pages["uses"] == ["Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main"], repo


def test_release_failures_are_excluded_from_leaf_qualification() -> None:
    evidence = _evidence()
    assert evidence["qualification"]["source_release_success_claimed"] is False
    assert all(not row["release"]["evidence_claimed"] for row in evidence["repos"].values())
    assert {failure["run"] for failure in evidence["excluded_release_failures"]} == {
        40346866581,
        40346866654,
        40346882675,
        40346882493,
        40343912389,
    }


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
