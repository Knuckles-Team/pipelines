"""Immutable, test-only proof for the R101/R102/R106/R108 and R112-R115 train.

The two fixtures are bounded collector receipts captured from the same provider
main SHA. These tests replay the existing status reader and assert the captured
aggregate-hook and Pages evidence without invoking or changing consumer code.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS
from scripts.spec_dashboard_sources import read_records


FIXTURE_DIR = Path(__file__).parent / "fixtures/connector_spec_delivery"
FIXTURES = (
    FIXTURE_DIR / "consumer_train_r101_102_r106_r108.json",
    FIXTURE_DIR / "consumer_train_r112_115.json",
)
EXPECTED_PROVIDER = "a4f0f46cd7c21b5dfce13194d42f4a06b67f2a73"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_LEAVES = {"spec-status", "spec-decomposition", "spec-trailers"}
STATUS_CONFIG = {"sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}
EXPECTED_ROWS = {"R101", "R102", "R106", "R108", "R112", "R113", "R114", "R115"}
READY_SPEC_1 = {f"PIPE-CONNSPEC-R{number}.1" for number in (101, 102, 106, 108, 112, 113, 114, 115)}
READY_SPEC_2 = {
    "PIPE-CONNSPEC-R102.2",
    "PIPE-CONNSPEC-R108.2",
    "PIPE-CONNSPEC-R112.2",
    "PIPE-CONNSPEC-R114.2",
    "PIPE-CONNSPEC-R115.2",
}
READY_SPEC_3 = {"PIPE-CONNSPEC-R102.3"}


def _evidence() -> dict:
    shards = [json.loads(path.read_text(encoding="utf-8")) for path in FIXTURES]
    assert len(shards) == 2
    provider = shards[0]["provider"]
    repos: dict[str, dict] = {}
    central: dict[str, dict] = {}
    for shard in shards:
        assert shard["provider"] == provider
        repos.update(shard["repos"])
        central.update(shard["central_requirements"])
    assert {row["row"] for row in repos.values()} == {f"PIPE-CONNSPEC-{row}" for row in EXPECTED_ROWS}
    return {"provider": provider, "repos": repos, "central_requirements": central, "shards": shards}


def _status_records(root: Path, row: dict) -> list[dict]:
    status = row["status"]
    for relative, content in status["status_source"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        assert hashlib.sha256(content.encode()).hexdigest() == status["status_file_sha256"][relative]
        assert json.loads(content) == status["status_documents"][relative]
    return read_records(root, STATUS_CONFIG)


@pytest.mark.spec("PIPE-CONNSPEC-R101.1")
@pytest.mark.spec("PIPE-CONNSPEC-R102.1")
@pytest.mark.spec("PIPE-CONNSPEC-R106.1")
@pytest.mark.spec("PIPE-CONNSPEC-R108.1")
@pytest.mark.spec("PIPE-CONNSPEC-R112.1")
@pytest.mark.spec("PIPE-CONNSPEC-R113.1")
@pytest.mark.spec("PIPE-CONNSPEC-R114.1")
@pytest.mark.spec("PIPE-CONNSPEC-R115.1")
def test_consumer_status_sources_are_readable(tmp_path: Path):
    evidence = _evidence()
    provider = evidence["provider"]
    assert provider["sha"] == EXPECTED_PROVIDER
    assert provider["spec_group_source"] == "pipelines_hooks/cli.py:71-74"
    assert provider["spec_group"] == list(GROUPS["spec"])
    for name, row in evidence["repos"].items():
        spec_id = f"{row['row']}.1"
        assert row["strict_leaves"][spec_id] is True, name
        assert len(row["sha"]) == 40 and all(char in "0123456789abcdef" for char in row["sha"])
        status = row["status"]
        records = _status_records(tmp_path / name, row)
        assert len(records) == status["status_record_count"]
        assert sorted(record["id"] for record in records) == sorted(status["status_spec_ids"])
        assert all(record["delivery_state"] in {"SPECIFIED", "LANDED", "VERIFIED"} for record in records)


@pytest.mark.spec("PIPE-CONNSPEC-R101.1")
def test_fixture_preserves_consumer_source_fingerprints():
    evidence = _evidence()
    required = {".github/workflows/pipeline.yml", ".github/workflows/pages.yml", ".pre-commit-config.yaml"}
    for name, row in evidence["repos"].items():
        assert required <= set(row["source_files"]), name
        for relative, source in row["source_files"].items():
            if source is None:
                continue
            content = source["content"].encode()
            assert len(content) == source["bytes"], (name, relative)
            assert hashlib.sha256(content).hexdigest() == source["sha256"], (name, relative)


@pytest.mark.spec("PIPE-CONNSPEC-R102.2")
@pytest.mark.spec("PIPE-CONNSPEC-R108.2")
@pytest.mark.spec("PIPE-CONNSPEC-R112.2")
@pytest.mark.spec("PIPE-CONNSPEC-R114.2")
@pytest.mark.spec("PIPE-CONNSPEC-R115.2")
def test_consumer_aggregate_hooks_match_canonical_template():
    evidence = _evidence()
    provider = evidence["provider"]
    expected = provider["canonical_template"]
    assert expected["rev"] == "main"
    assert set(expected["hooks"]) == EXPECTED_HOOKS
    assert provider["spec_group"] == list(GROUPS["spec"])
    assert EXPECTED_SPEC_LEAVES <= set(GROUPS["spec"])
    qualified = {f"{row['row']}.2" for row in evidence["repos"].values() if row["strict_leaves"].get(f"{row['row']}.2")}
    assert qualified == READY_SPEC_2
    for name, row in evidence["repos"].items():
        if not row["strict_leaves"].get(f"{row['row']}.2"):
            continue
        hooks = row["precommit"]
        assert hooks["aggregate_ready"] is True, name
        assert hooks["validate_config"]["returncode"] == 0, name
        assert hooks["canonical_hooks"] == expected, name
        assert hooks["missing"] == [], name


@pytest.mark.spec("PIPE-CONNSPEC-R102.3")
def test_consumer_pages_are_current_and_published():
    evidence = _evidence()
    qualified = {f"{row['row']}.3" for row in evidence["repos"].values() if row["strict_leaves"].get(f"{row['row']}.3")}
    assert qualified == READY_SPEC_3
    row = evidence["repos"]["archimate-mcp"]
    pages = row["pages"]
    run = pages["hosted_run"]
    assert pages["caller_count"] == 1
    assert pages["required_paths"] is True
    assert pages["shape_ready"] is True
    assert pages["exact_source_publisher_ready"] is True
    assert pages["http_200_ready"] is True
    assert pages["with"]["content_source"] == "docs"
    assert pages["with"]["spec_dashboard_enabled"] is True
    assert pages["config"]["version"] == 1
    assert run["conclusion"] == "success"
    assert run["headSha"] == row["sha"]
    assert run["url"].startswith("https://github.com/Knuckles-Team/archimate-mcp/actions/runs/")
    assert pages["live_http"]["status"] == 200
    assert pages["live_http"]["has_spec_id"] is True
    assert pages["live_http"]["url"].endswith("/spec-delivery/")


@pytest.mark.parametrize("failed_gate", GROUPS["spec"])
def test_spec_aggregate_dispatches_every_member_and_propagates_failure(monkeypatch, failed_gate):
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


def test_collector_shards_are_disjoint_and_unpromoted():
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert {row["row"] for row in evidence["repos"].values()} == {f"PIPE-CONNSPEC-{row}" for row in EXPECTED_ROWS}
    for row in evidence["central_requirements"].values():
        for requirement in row.values():
            assert requirement["delivery_state"] == "SPECIFIED"
            assert requirement["landed_in"] == []
            assert requirement["verified_by"] == []


def test_unqualified_rows_remain_explicitly_held():
    evidence = _evidence()
    counts = {suffix: 0 for suffix in (".1", ".2", ".3", ".4")}
    for row in evidence["repos"].values():
        for suffix in counts:
            if row["strict_leaves"].get(f"{row['row']}{suffix}", False):
                counts[suffix] += 1
        assert not row["strict_leaves"].get(f"{row['row']}.4", False)
    assert counts == {".1": 8, ".2": 5, ".3": 1, ".4": 0}
