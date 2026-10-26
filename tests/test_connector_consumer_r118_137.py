"""Immutable, test-only proof for PIPE-CONNSPEC consumer rows R118-R137.

The fixture was collected from each consumer's exact origin/main SHA after
pipelines PR #292 merged. These tests replay the existing status reader and
assert the captured aggregate-hook and Pages evidence without invoking or
changing consumer code.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS
from scripts.spec_dashboard_sources import read_records


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r118_137.json"
EXPECTED_PROVIDER = "5a4414da360c2f500c898a24bde103f535d10514"
EXPECTED_HOOKS = {
    "connector-standard",
    "dependency-readiness",
    "secrets",
    "spec",
    "tests-fast",
}
EXPECTED_SPEC_LEAVES = {"spec-status", "spec-decomposition", "spec-trailers"}
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


@pytest.mark.spec("PIPE-CONNSPEC-R118.1")
@pytest.mark.spec("PIPE-CONNSPEC-R119.1")
@pytest.mark.spec("PIPE-CONNSPEC-R120.1")
@pytest.mark.spec("PIPE-CONNSPEC-R121.1")
@pytest.mark.spec("PIPE-CONNSPEC-R122.1")
@pytest.mark.spec("PIPE-CONNSPEC-R123.1")
@pytest.mark.spec("PIPE-CONNSPEC-R124.1")
@pytest.mark.spec("PIPE-CONNSPEC-R125.1")
@pytest.mark.spec("PIPE-CONNSPEC-R126.1")
@pytest.mark.spec("PIPE-CONNSPEC-R127.1")
@pytest.mark.spec("PIPE-CONNSPEC-R128.1")
@pytest.mark.spec("PIPE-CONNSPEC-R129.1")
@pytest.mark.spec("PIPE-CONNSPEC-R130.1")
@pytest.mark.spec("PIPE-CONNSPEC-R131.1")
@pytest.mark.spec("PIPE-CONNSPEC-R132.1")
@pytest.mark.spec("PIPE-CONNSPEC-R133.1")
@pytest.mark.spec("PIPE-CONNSPEC-R134.1")
@pytest.mark.spec("PIPE-CONNSPEC-R135.1")
@pytest.mark.spec("PIPE-CONNSPEC-R136.1")
@pytest.mark.spec("PIPE-CONNSPEC-R137.1")
def test_consumer_status_sources_are_readable(tmp_path):
    evidence = _evidence()
    assert evidence["provider"]["sha"] == EXPECTED_PROVIDER
    for name, row in evidence["repos"].items():
        assert len(row["sha"]) == 40 and all(char in "0123456789abcdef" for char in row["sha"])
        status = row["status"]
        records = _status_records(tmp_path / name, row)
        assert len(records) == status["status_record_count"]
        assert sorted(record["id"] for record in records) == sorted(status["status_spec_ids"])
        assert all(record["delivery_state"] in {"SPECIFIED", "LANDED", "VERIFIED"} for record in records)


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


@pytest.mark.spec("PIPE-CONNSPEC-R119.2")
@pytest.mark.spec("PIPE-CONNSPEC-R120.2")
@pytest.mark.spec("PIPE-CONNSPEC-R121.2")
@pytest.mark.spec("PIPE-CONNSPEC-R122.2")
@pytest.mark.spec("PIPE-CONNSPEC-R123.2")
@pytest.mark.spec("PIPE-CONNSPEC-R126.2")
@pytest.mark.spec("PIPE-CONNSPEC-R127.2")
@pytest.mark.spec("PIPE-CONNSPEC-R128.2")
@pytest.mark.spec("PIPE-CONNSPEC-R129.2")
@pytest.mark.spec("PIPE-CONNSPEC-R130.2")
@pytest.mark.spec("PIPE-CONNSPEC-R132.2")
@pytest.mark.spec("PIPE-CONNSPEC-R133.2")
@pytest.mark.spec("PIPE-CONNSPEC-R134.2")
@pytest.mark.spec("PIPE-CONNSPEC-R135.2")
@pytest.mark.spec("PIPE-CONNSPEC-R137.2")
def test_consumer_aggregate_hooks_match_canonical_template():
    evidence = _evidence()
    expected = evidence["provider"]["canonical_template"]
    assert expected["rev"] == "main"
    assert set(expected["hooks"]) == EXPECTED_HOOKS
    assert evidence["provider"]["spec_group_source"] == "pipelines_hooks/cli.py:71-74"
    assert evidence["provider"]["spec_group"] == list(GROUPS["spec"])
    assert EXPECTED_SPEC_LEAVES <= set(GROUPS["spec"])
    for name, row in evidence["repos"].items():
        if not row["strict_leaves"].get(f"{row['row']}.2"):
            continue
        hooks = row["precommit"]
        assert hooks["aggregate_ready"] is True, name
        assert hooks["validate_config"]["returncode"] == 0, name
        assert hooks["canonical_hooks"] == expected, name
        assert hooks["missing"] == [], name


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


@pytest.mark.spec("PIPE-CONNSPEC-R119.3")
@pytest.mark.spec("PIPE-CONNSPEC-R130.3")
@pytest.mark.spec("PIPE-CONNSPEC-R132.3")
@pytest.mark.spec("PIPE-CONNSPEC-R137.3")
def test_consumer_pages_are_current_and_published():
    evidence = _evidence()
    qualified = {name for name, row in evidence["repos"].items() if row["strict_leaves"].get(f"{row['row']}.3")}
    assert qualified == {"erpnext-agent", "jena-mcp", "keycloak-agent", "lgtm-mcp"}
    for name in sorted(qualified):
        row = evidence["repos"][name]
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
        assert run["url"].startswith(f"https://github.com/Knuckles-Team/{name}/actions/runs/")
        assert pages["live_http"]["status"] == 200
        assert pages["live_http"]["has_spec_id"] is True
        assert pages["live_http"]["url"].endswith("/spec-delivery/")


def test_unqualified_rows_remain_explicitly_unbound():
    evidence = _evidence()
    assert evidence["strict_leaf_counts"] == {".1": 20, ".2": 15, ".3": 4, ".4": 0}
    assert all(not row["strict_leaves"][f"{row['row']}.4"] for row in evidence["repos"].values())
