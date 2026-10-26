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
        assert pages["hosted_run"]["headSha"] == row["sha"]
        assert pages["hosted_run"]["url"].startswith(f"https://github.com/Knuckles-Team/{name}/actions/runs/")
        assert pages["http"]["status"] == 200
        assert pages["http"]["has_spec_id"] is True
        assert pages["http"]["url"].endswith("/spec-delivery/")


def test_unqualified_rows_remain_explicitly_unbound():
    evidence = _evidence()
    assert evidence["strict_leaf_counts"] == {".1": 9, ".2": 6, ".3": 4, ".4": 0}
    assert evidence["repos"]["ciso-assistant-api"]["strict_leaves"]["PIPE-CONNSPEC-R111.3"] is False
    assert evidence["repos"]["ciso-assistant-api"]["pages"]["hosted_run"] is None
    assert all(not row["strict_leaves"][f"{row['row']}.4"] for row in evidence["repos"].values())
