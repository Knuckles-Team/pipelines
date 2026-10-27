"""Source-bound proof for the merged connector Pages/skill qualification batch.

The fixture is collected from the exact merged ``origin/main`` commits after
the connector PRs landed.  It records public artifact observations alongside
the source-bound development skill bytes and the exact successful Pages run
plus live dashboard revision where available.  The ``.4`` assertion binds
only the literal development-skill criterion; package publication is separate
release evidence.  Historical ``.1`` and ``.2`` evidence is recounted in the
fixture but deliberately not promoted by this batch.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.cli import GROUPS
from scripts.spec_dashboard_sources import read_records


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r103_r152_public_batch.json"
EXPECTED_PROVIDER = "6ce28b9347c97c317937a6012d409183c314cbd5"
EXPECTED_PAGES = {
    "archivebox-api": "PIPE-CONNSPEC-R103.3",
    "gitlab-api": "PIPE-CONNSPEC-R125.3",
    "gramps-mcp": "PIPE-CONNSPEC-R126.3",
    "hdhomerun-mcp": "PIPE-CONNSPEC-R127.3",
    "jellyfin-mcp": "PIPE-CONNSPEC-R129.3",
    "langfuse-agent": "PIPE-CONNSPEC-R134.3",
    "leanix-agent": "PIPE-CONNSPEC-R135.3",
    "plane-agent": "PIPE-CONNSPEC-R152.3",
}
EXPECTED_SKILLS = {
    "archivebox-api": "PIPE-CONNSPEC-R103.4",
    "documentdb-mcp": "PIPE-CONNSPEC-R116.4",
    "gitlab-api": "PIPE-CONNSPEC-R125.4",
    "gramps-mcp": "PIPE-CONNSPEC-R126.4",
    "hdhomerun-mcp": "PIPE-CONNSPEC-R127.4",
    "jellyfin-mcp": "PIPE-CONNSPEC-R129.4",
    "lakekeeper-mcp": "PIPE-CONNSPEC-R133.4",
    "langfuse-agent": "PIPE-CONNSPEC-R134.4",
    "leanix-agent": "PIPE-CONNSPEC-R135.4",
    "plane-agent": "PIPE-CONNSPEC-R152.4",
}
HELD_ROWS = {
    "PIPE-CONNSPEC-R116.3",
    "PIPE-CONNSPEC-R133.3",
    "PIPE-CONNSPEC-R136.3",
    "PIPE-CONNSPEC-R136.4",
}
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
REQUIRED_PAGE_PATHS = {
    "specs/**",
    ".github/spec-dashboard.json",
    ".github/workflows/pages.yml",
}
STATUS_CONFIG = {"sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _status_records(root: Path, row: dict) -> list[dict]:
    status = row["status"]
    for relative, content in status["status_source"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        assert hashlib.sha256(content.encode()).hexdigest() == status["status_file_sha256"][relative]
        assert json.loads(content) == status["status_documents"][relative]
    return read_records(root, STATUS_CONFIG)


def _workflow(row: dict) -> tuple[dict, dict]:
    document = yaml.safe_load(row["source_files"][".github/workflows/pages.yml"]["content"]) or {}
    trigger = document.get("on", document.get(True, {})) or {}
    jobs = document.get("jobs") or {}
    pages = [
        job for job in jobs.values() if isinstance(job, dict) and "/pages_pipeline.yml@" in str(job.get("uses", ""))
    ]
    assert len(pages) == 1
    return pages[0], trigger


@pytest.mark.spec("PIPE-CONNSPEC-R103.3")
@pytest.mark.spec("PIPE-CONNSPEC-R125.3")
@pytest.mark.spec("PIPE-CONNSPEC-R126.3")
@pytest.mark.spec("PIPE-CONNSPEC-R127.3")
@pytest.mark.spec("PIPE-CONNSPEC-R129.3")
@pytest.mark.spec("PIPE-CONNSPEC-R134.3")
@pytest.mark.spec("PIPE-CONNSPEC-R135.3")
@pytest.mark.spec("PIPE-CONNSPEC-R152.3")
def test_pages_are_exact_merged_source_published() -> None:
    evidence = _evidence()
    qualified = {name for name, row in evidence["repos"].items() if row["strict_leaves"].get(f"{row['row']}.3")}
    assert qualified == set(EXPECTED_PAGES)
    for name, requirement_id in EXPECTED_PAGES.items():
        row = evidence["repos"][name]
        job, trigger = _workflow(row)
        page = row["pages"]
        assert row["strict_leaves"][requirement_id] is True
        assert job["uses"] == "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main"
        assert page["caller_count"] == 1
        assert page["with"]["content_source"] == "docs"
        assert page["with"]["spec_dashboard_enabled"] is True
        assert page["with"]["spec_dashboard_config"] == ".github/spec-dashboard.json"
        assert page["config"] == {"version": 1, "sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}
        assert set((trigger.get("push") or {}).get("paths") or []) >= REQUIRED_PAGE_PATHS
        hosted = page["hosted_run"]
        assert hosted["conclusion"] == "success"
        assert hosted["head_sha"] == row["sha"]
        assert hosted["path"] == ".github/workflows/pages.yml"
        api = page["pages_api"]
        assert api["build_type"] == "workflow"
        assert api["public"] is True
        assert api["https_enforced"] is True
        assert api["source"] == {"branch": "main", "path": "/"}
        live = page["live"]
        assert live["status"] == 200
        assert live["bytes"] > 0
        assert live["has_spec_id"] is True
        snapshot = page["snapshot"]
        assert snapshot["status"] == 200
        assert snapshot["revision"] == row["sha"]


@pytest.mark.spec("PIPE-CONNSPEC-R103.4")
@pytest.mark.spec("PIPE-CONNSPEC-R116.4")
@pytest.mark.spec("PIPE-CONNSPEC-R125.4")
@pytest.mark.spec("PIPE-CONNSPEC-R126.4")
@pytest.mark.spec("PIPE-CONNSPEC-R127.4")
@pytest.mark.spec("PIPE-CONNSPEC-R129.4")
@pytest.mark.spec("PIPE-CONNSPEC-R133.4")
@pytest.mark.spec("PIPE-CONNSPEC-R134.4")
@pytest.mark.spec("PIPE-CONNSPEC-R135.4")
@pytest.mark.spec("PIPE-CONNSPEC-R152.4")
def test_development_skills_are_source_bound() -> None:
    evidence = _evidence()
    qualified = {name for name, row in evidence["repos"].items() if row["strict_leaves"].get(f"{row['row']}.4")}
    assert qualified == set(EXPECTED_SKILLS)
    for name, requirement_id in EXPECTED_SKILLS.items():
        row = evidence["repos"][name]
        skill = row["skill"]
        assert row["strict_leaves"][requirement_id] is True
        assert skill["path"] in row["source_files"]
        source = row["source_files"][skill["path"]]
        assert source["bytes"] == skill["bytes"]
        assert source["sha256"] == skill["sha256"]
        assert "## Rapid delivery: the 5-minute contract" in source["content"]


def test_source_and_status_snapshots_are_immutable_and_historical_leaves_remain() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert evidence["provider"]["canonical_template"]["rev"] == "main"
    assert set(evidence["provider"]["canonical_template"]["hooks"]) == EXPECTED_HOOKS
    assert evidence["provider"]["spec_group"] == list(GROUPS["spec"])
    for name, row in evidence["repos"].items():
        assert row["sha"] == row["candidate_sha"]
        for relative, source in row["source_files"].items():
            content = source["content"].encode()
            assert len(content) == source["bytes"], (name, relative)
            assert hashlib.sha256(content).hexdigest() == source["sha256"], (name, relative)
        records = _status_records(Path("/tmp") / f"central-status-{name}", row)
        assert len(records) == row["status"]["status_record_count"]
        assert sorted(str(record["id"]) for record in records) == row["status"]["status_spec_ids"]
        assert all(record["delivery_state"] in {"SPECIFIED", "LANDED", "VERIFIED", "RETIRED"} for record in records)
        assert all(row["strict_leaves"].get(f"{row['row']}.{suffix}") is False for suffix in ("1", "2"))
        for requirement_id in row["historical_verified_leaves"]:
            row_number = requirement_id.split("-")[2][1:].split(".", 1)[0]
            assert evidence["central_requirements"][row_number][requirement_id]["delivery_state"] == "VERIFIED"


@pytest.mark.parametrize("failed_gate", GROUPS["spec"])
def test_spec_aggregate_dispatches_every_member_and_propagates_failure(monkeypatch, failed_gate):
    """The central aggregate remains equivalent to its four source gates."""
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


def test_unqualified_rows_remain_explicitly_held() -> None:
    evidence = _evidence()
    assert evidence["strict_leaf_counts"] == {".1": 0, ".2": 0, ".3": 8, ".4": 10}
    for requirement_id in HELD_ROWS:
        row = next(row for row in evidence["repos"].values() if requirement_id in row["strict_leaves"])
        assert row["strict_leaves"][requirement_id] is False
    assert evidence["qualification"]["rollups_promoted"] is True
    assert evidence["qualification"]["promoted_rollups"] == [
        "PIPE-CONNSPEC-R116",
        "PIPE-CONNSPEC-R126",
        "PIPE-CONNSPEC-R127",
        "PIPE-CONNSPEC-R129",
        "PIPE-CONNSPEC-R134",
        "PIPE-CONNSPEC-R135",
    ]
    assert evidence["qualification"]["source_release_success_claimed"] is False
