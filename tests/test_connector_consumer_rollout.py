"""Immutable, test-only proof for the connector spec-delivery rollout.

The fixture is produced from the consumer repositories' exact ``origin/main``
commits by the bounded proof command named in its metadata. These tests do not
change or invoke consumer code: they re-run the existing status reader against
the captured status documents and assert the captured central-hook and hosted
Pages evidence. A missing or stale proof field fails closed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS
from scripts.spec_dashboard_sources import read_records


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train.json"
EXPECTED_PROVIDER = "5c1de08df84e4e67ebc4fd04210626135c336de9"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_CADDY_SKILL = "caddy_mcp/skills/caddy-mcp-development/SKILL.md"
STATUS_CONFIG = {"sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _status_records(root: Path, row: dict) -> list[dict]:
    for relative, content in row["status_source"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        assert hashlib.sha256(content.encode()).hexdigest() == row["status_file_sha256"][relative]
        assert json.loads(content) == row["status_documents"][relative]
    return read_records(root, STATUS_CONFIG)


@pytest.mark.spec("PIPE-CONNSPEC-R103.1")
@pytest.mark.spec("PIPE-CONNSPEC-R104.1")
@pytest.mark.spec("PIPE-CONNSPEC-R105.1")
@pytest.mark.spec("PIPE-CONNSPEC-R107.1")
@pytest.mark.spec("PIPE-CONNSPEC-R109.1")
@pytest.mark.spec("PIPE-CONNSPEC-R110.1")
@pytest.mark.spec("PIPE-CONNSPEC-R111.1")
@pytest.mark.spec("PIPE-CONNSPEC-R116.1")
@pytest.mark.spec("PIPE-CONNSPEC-R117.1")
def test_consumer_status_sources_are_readable(tmp_path):
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    for name, row in evidence["repos"].items():
        assert len(row["sha"]) == 40 and all(char in "0123456789abcdef" for char in row["sha"])
        records = _status_records(tmp_path / name, row)
        assert len(records) == row["status_record_count"]
        assert sorted(record["id"] for record in records) == sorted(row["status_spec_ids"])
        assert all(record["delivery_state"] in {"SPECIFIED", "LANDED", "VERIFIED"} for record in records)


def test_fixture_preserves_consumer_source_fingerprints():
    evidence = _evidence()
    required = {".github/workflows/pipeline.yml", ".github/workflows/pages.yml", ".pre-commit-config.yaml"}
    for name, row in evidence["repos"].items():
        assert required <= set(row["source_files"]), name
        for relative, source in row["source_files"].items():
            content = source["content"].encode()
            assert len(content) == source["bytes"], (name, relative)
            assert hashlib.sha256(content).hexdigest() == source["sha256"], (name, relative)


@pytest.mark.spec("PIPE-CONNSPEC-R104.2")
@pytest.mark.spec("PIPE-CONNSPEC-R105.2")
@pytest.mark.spec("PIPE-CONNSPEC-R107.2")
@pytest.mark.spec("PIPE-CONNSPEC-R109.2")
@pytest.mark.spec("PIPE-CONNSPEC-R110.2")
@pytest.mark.spec("PIPE-CONNSPEC-R117.2")
def test_consumer_aggregate_hooks_match_canonical_template():
    evidence = _evidence()
    expected = evidence["provider"]["canonical_template"]
    assert expected["rev"] == "main"
    assert set(expected["hooks"]) == EXPECTED_HOOKS
    assert evidence["provider"]["spec_group_source"] == "pipelines_hooks/cli.py:73"
    assert evidence["provider"]["spec_group"] == list(GROUPS["spec"])
    assert set(evidence["provider"]["spec_leaf_hooks"]) <= set(GROUPS["spec"])
    for name, row in evidence["repos"].items():
        hooks = row["precommit"]
        if not all(row["strict_leaves"].get(f"{row['row']}.{suffix}") for suffix in ("2",)):
            continue
        assert hooks["validate_config_rc"] == 0, name
        assert hooks["provider_rev"] == expected["rev"], name
        assert set(expected["hooks"]) <= set(hooks["hooks"]), name
        assert hooks["missing_canonical"] == [], name


@pytest.mark.parametrize("failed_gate", GROUPS["spec"])
def test_spec_aggregate_dispatches_every_member_and_propagates_failure(monkeypatch, failed_gate):
    """The canonical aggregate remains equivalent to its four source gates."""
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


@pytest.mark.spec("PIPE-CONNSPEC-R104.3")
@pytest.mark.spec("PIPE-CONNSPEC-R109.3")
@pytest.mark.spec("PIPE-CONNSPEC-R110.3")
@pytest.mark.spec("PIPE-CONNSPEC-R117.3")
def test_consumer_pages_are_current_and_published(tmp_path):
    evidence = _evidence()
    qualified = {name for name, row in evidence["repos"].items() if row["strict_leaves"].get(f"{row['row']}.3")}
    assert qualified == {"aris-mcp", "caddy-mcp", "camunda-mcp", "egeria-mcp"}
    for name in sorted(qualified):
        row = evidence["repos"][name]
        pages = row["pages"]
        assert pages["caller_count"] == 1
        assert pages["required_paths"] is True
        assert pages["with"]["content_source"] == "docs"
        assert pages["with"]["spec_dashboard_enabled"] is True
        assert pages["config"]["version"] == 1
        assert pages["hosted_run"]["conclusion"] == "success"
        assert pages["hosted_run"]["headSha"] == pages.get("historical_source_sha", row["sha"])
        assert pages["hosted_run"]["url"].startswith(f"https://github.com/Knuckles-Team/{name}/actions/runs/")
        assert pages["http"]["status"] == 200
        assert pages["http"]["has_spec_id"] is True
        assert pages["http"]["url"].endswith("/spec-delivery/")


@pytest.mark.spec("PIPE-CONNSPEC-R109.4")
def test_caddy_rapid_delivery_skill_and_pages_are_source_backed():
    row = _evidence()["repos"]["caddy-mcp"]
    assert row["skill_path"] == EXPECTED_CADDY_SKILL
    skill = row["source_files"][EXPECTED_CADDY_SKILL]["content"]
    assert "## Rapid delivery: the 5-minute contract" in skill
    for source_reference in (
        "caddy_mcp/__init__.py",
        "CADDY_TOKEN",
        "agent_connector_sdk.cli:serve",
        "uvx pre-commit",
    ):
        assert source_reference in skill

    pages = row["pages"]
    assert pages["known_pages_run"] == "40425009250"
    assert pages["hosted_run"]["databaseId"] == 40425009250
    assert pages["hosted_run"]["headSha"] == row["sha"]
    assert pages["http"]["status"] == 200


EXPECTED_PACKAGE_PUBLICATIONS = {
    "aris-mcp": {
        "source_sha": "c5df897fa6e4ff561c21c5d57c74f513f0ff2e3d",
        "skill": "aris_mcp/skills/aris-mcp-development/SKILL.md",
        "skill_bytes": 5100,
        "skill_sha256": "94d4bd078892fd8d11e636164d8585b06d98f61882f891f8d6e079e09069af1d",
        "skill_terms": (
            "aris_mcp/__init__.py",
            "ARIS_API_BASE",
            "ARIS_TLS_PROFILE",
            "connector: true",
            "render_connector: true",
        ),
        "package_run": 40431780316,
        "version": "1.3.6",
        "wheel_sha256": "3a037cc88107c8f08ed21672d081b7bea42365a2e89affbf245412357c8c8ecf",
        "sdist_sha256": "5bb52c6c5c804a0df9d40500a52a5da592eb68c681a83a90c4b1fbc126e11949",
    },
    "camunda-mcp": {
        "source_sha": "933b2f44838535b621b999b1499b076efe564978",
        "skill": "camunda_mcp/skills/camunda-mcp-development/SKILL.md",
        "skill_bytes": 6541,
        "skill_sha256": "abb84ee6c269a6d91b9c363b1d72d492142d6ca2ef2b20871f91e43a0e1ecaba",
        "skill_terms": (
            "camunda_mcp/__init__.py",
            "CAMUNDA7_URL",
            "CAMUNDA_TLS_PROFILE",
            "connector: true",
            "render_connector: true",
        ),
        "package_run": 40431609053,
        "version": "2.6.6",
        "wheel_sha256": "519ed5339c1db3a1e8d2f793e2547c0bacb47b08df2576ca11451c4e59a03b49",
        "sdist_sha256": "a3b612e6b52bf8df34b08e79c7374044118773c0c2879364ce4e7f15782ebba5",
    },
    "egeria-mcp": {
        "source_sha": "d6c0e954f2c21fcde036a5b5e98535927cf3f3d8",
        "skill": "egeria_mcp/skills/egeria-mcp-development/SKILL.md",
        "skill_bytes": 6017,
        "skill_sha256": "8182f38abf51e441fe67b32c782592232b45f55cf7953dd27d3fbab16c35b93c",
        "skill_terms": (
            "egeria_mcp/__init__.py",
            "EGERIA_PLATFORM_URL",
            "EGERIA_ENABLE_WRITE",
            "connector: true",
            "render_connector: true",
        ),
        "package_run": 40432274511,
        "version": "2.3.5",
        "wheel_sha256": "7eb94348b0537fe577f5fc5e69b19b9a326234ed9e39f9e1ec82a5f8fc3f1568",
        "sdist_sha256": "390538705d651763e3cde80415eff2e451730aa4edf0360fc87e58fe7adfbaa1",
    },
}


@pytest.mark.spec("PIPE-CONNSPEC-R104.4")
@pytest.mark.spec("PIPE-CONNSPEC-R110.4")
@pytest.mark.spec("PIPE-CONNSPEC-R117.4")
def test_package_only_skills_are_bound_to_exact_public_artifacts():
    evidence = _evidence()
    for name, expected in EXPECTED_PACKAGE_PUBLICATIONS.items():
        row = evidence["repos"][name]
        assert row["sha"] == row["candidate_sha"] == expected["source_sha"]
        assert row["strict_leaves"][f"{row['row']}.4"] is True
        assert row["skill_path"] == expected["skill"]

        source = row["source_files"][expected["skill"]]
        content = source["content"].encode()
        assert source["bytes"] == expected["skill_bytes"]
        assert len(content) == source["bytes"]
        assert hashlib.sha256(content).hexdigest() == source["sha256"] == expected["skill_sha256"]
        assert "## Rapid delivery: the 5-minute contract" in source["content"]
        for term in expected["skill_terms"]:
            assert term in source["content"], (name, term)

        publication = row["publication"]
        assert publication["source_sha"] == expected["source_sha"]
        assert publication["package_run"] == expected["package_run"]
        assert publication["package_conclusion"] == "success"
        assert publication["version"] == expected["version"]
        assert publication["wheel_sha256"] == expected["wheel_sha256"]
        assert publication["sdist_sha256"] == expected["sdist_sha256"]
        assert publication["skill_sha256"] == expected["skill_sha256"]
        assert publication["wheel_contains_skill"] is True
        assert publication["sdist_contains_skill"] is True


def test_unqualified_rows_remain_explicitly_unbound():
    evidence = _evidence()
    assert evidence["strict_leaf_counts"] == {".1": 9, ".2": 6, ".3": 4, ".4": 4}
    assert evidence["repos"]["ciso-assistant-api"]["strict_leaves"]["PIPE-CONNSPEC-R111.3"] is False
    assert evidence["repos"]["ciso-assistant-api"]["pages"]["hosted_run"] is None
    assert evidence["repos"]["caddy-mcp"]["strict_leaves"]["PIPE-CONNSPEC-R109.4"] is True
    assert [name for name, row in evidence["repos"].items() if row["strict_leaves"][f"{row['row']}.4"]] == [
        "aris-mcp",
        "caddy-mcp",
        "camunda-mcp",
        "egeria-mcp",
    ]
