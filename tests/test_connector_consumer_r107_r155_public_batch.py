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
EXPECTED_PAGES = {
    "audio-transcriber": "PIPE-CONNSPEC-R107.3",
    "ciso-assistant-api": "PIPE-CONNSPEC-R111.3",
    "fan-manager": "PIPE-CONNSPEC-R120.3",
    "home-assistant-agent": "PIPE-CONNSPEC-R128.3",
}
EXPECTED_SKILLS = {
    "audio-transcriber": "PIPE-CONNSPEC-R107.4",
    "ciso-assistant-api": "PIPE-CONNSPEC-R111.4",
    "erpnext-agent": "PIPE-CONNSPEC-R119.4",
    "fan-manager": "PIPE-CONNSPEC-R120.4",
    "freshrss-agent": "PIPE-CONNSPEC-R122.4",
    "home-assistant-agent": "PIPE-CONNSPEC-R128.4",
    "jena-mcp": "PIPE-CONNSPEC-R130.4",
    "keycloak-agent": "PIPE-CONNSPEC-R132.4",
    "pulselink-mcp": "PIPE-CONNSPEC-R155.4",
}
HELD_ROWS = {
    "PIPE-CONNSPEC-R118.3",
    "PIPE-CONNSPEC-R118.4",
    "PIPE-CONNSPEC-R122.3",
    "PIPE-CONNSPEC-R131.3",
    "PIPE-CONNSPEC-R131.4",
    "PIPE-CONNSPEC-R155.3",
    "PIPE-CONNSPEC-R156.3",
    "PIPE-CONNSPEC-R156.4",
}
HISTORICAL_VERIFIED = {
    "PIPE-CONNSPEC-R107.1",
    "PIPE-CONNSPEC-R107.2",
    "PIPE-CONNSPEC-R155.1",
}


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
@pytest.mark.spec("PIPE-CONNSPEC-R111.3")
@pytest.mark.spec("PIPE-CONNSPEC-R120.3")
@pytest.mark.spec("PIPE-CONNSPEC-R128.3")
def test_pages_are_published_from_exact_main() -> None:
    evidence = _evidence()
    evidence = _evidence()
    assert {name for name, row in evidence["repos"].items() if "pages" in row} == set(EXPECTED_PAGES)
    for name, requirement_id in EXPECTED_PAGES.items():
        row = evidence["repos"][name]
        page = row["pages"]
        caller_source, _ = _source(row, ".github/workflows/pages.yml")
        config_source, _ = _source(row, page["config_path"])
        caller = yaml.safe_load(caller_source["content"])
        trigger = caller.get("on", caller.get(True, {})) or {}
        publishers = [
            job
            for job in (caller.get("jobs") or {}).values()
            if isinstance(job, dict) and job.get("uses") == page["uses"]
        ]
        assert len(publishers) == page["caller_count"] == 1
        assert page["uses"] == "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main"
        assert publishers[0]["with"].items() >= page["with"].items()
        assert page["with"]["spec_dashboard_enabled"] is True
        assert page["with"]["spec_dashboard_config"] == page["config_path"]
        assert json.loads(config_source["content"]) == page["config"]
        assert page["config"] == {
            "version": 1,
            "sources": [{"glob": "specs/*/status.json", "kind": "spec"}],
        }
        assert set(trigger["push"]["paths"]) >= {
            "specs/**",
            page["config_path"],
            ".github/workflows/pages.yml",
        }
        assert row["sha"] == row["candidate_sha"]
        assert requirement_id in row["qualified_leaves"]
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
@pytest.mark.spec("PIPE-CONNSPEC-R111.4")
@pytest.mark.spec("PIPE-CONNSPEC-R119.4")
@pytest.mark.spec("PIPE-CONNSPEC-R120.4")
@pytest.mark.spec("PIPE-CONNSPEC-R122.4")
@pytest.mark.spec("PIPE-CONNSPEC-R128.4")
@pytest.mark.spec("PIPE-CONNSPEC-R130.4")
@pytest.mark.spec("PIPE-CONNSPEC-R132.4")
@pytest.mark.spec("PIPE-CONNSPEC-R155.4")
def test_development_skills_are_source_bound() -> None:
    evidence = _evidence()
    assert {name for name, row in evidence["repos"].items() if "skill" in row} == set(EXPECTED_SKILLS)
    for name, requirement_id in EXPECTED_SKILLS.items():
        row = evidence["repos"][name]
        skill = row["skill"]
        source, _ = _source(row, skill["path"])
        assert row["sha"] == row["candidate_sha"]
        assert requirement_id in row["qualified_leaves"]
        assert skill["rapid_heading"] is True
        assert skill["bytes"] == source["bytes"]
        assert skill["sha256"] == source["sha256"]
        assert "## Rapid delivery: the 5-minute contract" in source["content"]


def test_fixture_preserves_exact_main_status_and_only_new_qualifications() -> None:
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    assert evidence["provider"]["canonical_template"]["rev"] == "main"
    assert evidence["strict_leaf_counts"] == {".3": len(EXPECTED_PAGES), ".4": len(EXPECTED_SKILLS)}
    assert evidence["qualification"]["new_pages_rows"] == sorted(EXPECTED_PAGES.values())
    assert set(evidence["qualification"]["new_skill_rows"]) == set(EXPECTED_SKILLS.values())
    assert set(evidence["qualification"]["held_rows"]) == HELD_ROWS
    assert set(evidence["qualification"]["historical_verified_leaves"]) == HISTORICAL_VERIFIED
    assert evidence["qualification"]["rollups_promoted"] is True
    assert evidence["qualification"]["promoted_rollups"] == [
        "PIPE-CONNSPEC-R107",
        "PIPE-CONNSPEC-R119",
        "PIPE-CONNSPEC-R120",
        "PIPE-CONNSPEC-R128",
        "PIPE-CONNSPEC-R130",
        "PIPE-CONNSPEC-R132",
    ]
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
