"""Behavioral coverage for the extracted public status receipt validator."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_public_specs import status_errors as command_status_errors
from scripts.public_spec_status import status_errors

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40


def status():
    return dict(schema_version=1, spec_id="PIPE-TEST-1", owner_repo="pipelines",
                requirement_ids=["TEST-1"], delivery_state="SPECIFIED",
                acceptance_state="NOT_AUDITED", evidence=[])


def evidence(kind, *, commit=COMMIT, result="passed"):
    return {"kind": kind, "commit": commit, "result": result, "description": "Verified receipt",
            "url": f"https://github.com/Knuckles-Team/pipelines/commit/{commit}"}


def check(tmp_path, data):
    path = tmp_path / "status.json"
    path.write_text(json.dumps(data))
    return status_errors(path)


@pytest.mark.parametrize("payload,reason", [("{", "invalid JSON"), ("[]", "status must be an object")])
def test_invalid_status_json(tmp_path, payload, reason):
    path = tmp_path / "status.json"
    path.write_text(payload)
    errors, ids, spec_id = status_errors(path)
    assert len(errors) == 1 and reason in errors[0]
    assert (ids, spec_id) == ([], "")


@pytest.mark.parametrize("field,value,reason", [
    ("schema_version", 2, "schema version or spec ID mismatch"),
    ("owner_repo", "other", "wrong owner"),
    ("requirement_ids", [], "requirement IDs required"),
    ("delivery_state", "INVALID", "invalid state"),
    ("acceptance_state", "INVALID", "invalid state"),
    ("evidence", {}, "evidence must be an array"),
    ("evidence", [None], "evidence item must be an object"),
    ("evidence", [{}], "invalid public evidence receipt"),
])
def test_status_contract_errors(tmp_path, field, value, reason):
    data = status()
    data[field] = value
    errors, _, _ = check(tmp_path, data)
    assert len(errors) == 1 and reason in errors[0]


@pytest.mark.parametrize("receipt_kind", ["consumer", "release"])
def test_acceptance_requires_matching_public_receipts(tmp_path, receipt_kind):
    data = status()
    data.update(delivery_state="LANDED", acceptance_state="ACCEPTED",
                evidence=[evidence(kind) for kind in ("merged_head", "test", receipt_kind)])
    assert check(tmp_path, data) == ([], ["TEST-1"], "PIPE-TEST-1")
    data["evidence"][-1]["commit"] = "b" * 40
    assert any("acceptance receipts required" in error for error in check(tmp_path, data)[0])


@pytest.mark.parametrize("state", ["LANDED", "CLOSED"])
def test_landed_requires_successful_merged_head(tmp_path, state):
    data = status()
    data.update(delivery_state=state, evidence=[evidence("merged_head", result="failed")])
    assert any("merged-head evidence required" in error for error in check(tmp_path, data)[0])
    data["evidence"][0] = evidence("merged_head")
    assert check(tmp_path, data)[0] == []


@pytest.mark.parametrize("args", [["scripts/check_public_specs.py"], ["-m", "scripts.check_public_specs"]])
def test_direct_and_module_entrypoints(args):
    assert command_status_errors is status_errors
    result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Public pipeline specs are structurally complete and self-contained.\n"
