"""Main-bound evidence for the next connector Pages and skill leaves."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.spec_dashboard_sources import read_records


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r107_r155_public_batch.json"
EXPECTED_PROVIDER = "40fe75b242094ccfaf3c3406df0852deffcee57e"
STATUS_CONFIG = {"sources": [{"glob": "specs/*/status.json", "kind": "spec"}]}
EXPECTED_PAGES = "PIPE-CONNSPEC-R107.3"
EXPECTED_SKILLS = {"audio-transcriber": "PIPE-CONNSPEC-R107.4", "pulselink-mcp": "PIPE-CONNSPEC-R155.4"}
HELD_ROWS = {"PIPE-CONNSPEC-R155.3", "PIPE-CONNSPEC-R156.3", "PIPE-CONNSPEC-R156.4"}
HISTORICAL_VERIFIED = {"PIPE-CONNSPEC-R107.1", "PIPE-CONNSPEC-R107.2", "PIPE-CONNSPEC-R155.1"}


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _status_records(repo: str, row: dict) -> list[dict]:
    root = Path("/tmp") / f"central-status-r107-r155-{repo}"
    for relative, content in row["status"]["status_source"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        assert hashlib.sha256(content.encode()).hexdigest() == row["status"]["status_file_sha256"][relative]
        assert json.loads(content) == row["status"]["status_documents"][relative]
    return read_records(root, STATUS_CONFIG)


def _source(row: dict, path: str) -> tuple[dict, bytes]:
    source = row["source_files"][path]
    content = source["content"].encode()
    assert source["path"] == path
    assert source["bytes"] == len(content)
    assert source["sha256"] == hashlib.sha256(content).hexdigest()
    return source, content


@pytest.mark.spec("PIPE-CONNSPEC-R107.3")
def test_audio_transcriber_pages_are_published_from_exact_main() -> None:
    evidence = _evidence()
    row = evidence["repos"]["audio-transcriber"]
    caller_source, _ = _source(row, ".github/workflows/pages.yml")
    config_source, _ = _source(row, ".github/spec-dashboard.json")
    caller = yaml.safe_load(caller_source["content"])
    trigger = caller.get("on", caller.get(True, {})) or {}
    publishers = [
        job
        for job in (caller.get("jobs") or {}).values()
        if isinstance(job, dict)
        and job.get("uses") == "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main"
    ]
    assert len(publishers) == 1
    assert publishers[0]["with"]["spec_dashboard_enabled"] is True
    assert publishers[0]["with"]["spec_dashboard_config"] == ".github/spec-dashboard.json"
    assert json.loads(config_source["content"]) == {
        "version": 1,
        "sources": [{"glob": "specs/*/status.json", "kind": "spec"}],
    }
    assert set(trigger["push"]["paths"]) >= {"specs/**", ".github/spec-dashboard.json", ".github/workflows/pages.yml"}

    page = row["pages"]
    assert row["sha"] == row["candidate_sha"]
    assert page["caller_count"] == 1
    assert page["uses"] == "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main"
    assert page["with"] == {
        "spec_dashboard_enabled": True,
        "spec_dashboard_config": ".github/spec-dashboard.json",
    }
    assert page["pages_api"]["public"] is True
    assert page["pages_api"]["https_enforced"] is True
    assert page["pages_api"]["source"] == {"branch": "main", "path": "/"}
    assert page["hosted_run"]["conclusion"] == "success"
    assert page["expected_pages_run"] == page["hosted_run"]["id"]
    assert page["hosted_run"]["head_sha"] == row["sha"]
    assert page["hosted_run"]["path"] == ".github/workflows/pages.yml"
    assert page["live"]["status"] == 200 and page["live"]["bytes"] > 0
    assert page["live"]["has_spec_id"] is True
    assert page["live"]["spec_id"] in row["status"]["status_spec_ids"]
    assert page["snapshot"]["status"] == 200
    assert page["snapshot"]["revision"] == row["sha"]


@pytest.mark.spec("PIPE-CONNSPEC-R107.4")
def test_audio_transcriber_development_skill_is_on_exact_main() -> None:
    evidence = _evidence()
    row = evidence["repos"]["audio-transcriber"]
    skill = row["skill"]
    source, _ = _source(row, skill["path"])
    assert row["sha"] == row["candidate_sha"]
    assert skill["rapid_heading"] is True
    assert "## Rapid delivery: the 5-minute contract" in source["content"]


@pytest.mark.spec("PIPE-CONNSPEC-R155.4")
def test_pulselink_development_skill_is_on_exact_main() -> None:
    evidence = _evidence()
    row = evidence["repos"]["pulselink-mcp"]
    skill = row["skill"]
    source, _ = _source(row, skill["path"])
    assert row["sha"] == row["candidate_sha"]
    assert skill["rapid_heading"] is True
    assert "## Rapid delivery: the 5-minute contract" in source["content"]


def test_fixture_preserves_exact_main_status_and_only_new_qualifications() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert evidence["provider"]["canonical_template"]["rev"] == "main"
    assert evidence["strict_leaf_counts"] == {".3": 1, ".4": 2}
    assert evidence["qualification"]["new_pages_rows"] == [EXPECTED_PAGES]
    assert set(evidence["qualification"]["new_skill_rows"]) == set(EXPECTED_SKILLS.values())
    assert set(evidence["qualification"]["held_rows"]) == HELD_ROWS
    assert set(evidence["qualification"]["historical_verified_leaves"]) == HISTORICAL_VERIFIED
    assert evidence["qualification"]["rollups_promoted"] is True
    assert evidence["qualification"]["promoted_rollups"] == ["PIPE-CONNSPEC-R107"]
    assert evidence["qualification"]["source_release_success_claimed"] is False

    for name, row in evidence["repos"].items():
        assert row["sha"] == row["candidate_sha"]
        for relative, source in row["source_files"].items():
            content = source["content"].encode()
            assert source["bytes"] == len(content), (name, relative)
            assert source["sha256"] == hashlib.sha256(content).hexdigest(), (name, relative)
        records = _status_records(name, row)
        assert len(records) == row["status"]["status_record_count"]
        assert sorted(str(record["id"]) for record in records) == row["status"]["status_spec_ids"]
        assert all(record["delivery_state"] in {"SPECIFIED", "LANDED", "VERIFIED", "RETIRED"} for record in records)
        for requirement_id in row["qualified_leaves"]:
            number = requirement_id.split("-")[2][1:].split(".", 1)[0]
            assert evidence["central_requirements"][number][requirement_id]["delivery_state"] == "SPECIFIED"
    for requirement_id in HELD_ROWS:
        number = requirement_id.split("-")[2][1:].split(".", 1)[0]
        assert evidence["central_requirements"][number][requirement_id]["delivery_state"] == "SPECIFIED"
    for requirement_id in HISTORICAL_VERIFIED:
        number = requirement_id.split("-")[2][1:].split(".", 1)[0]
        assert evidence["central_requirements"][number][requirement_id]["delivery_state"] == "VERIFIED"
