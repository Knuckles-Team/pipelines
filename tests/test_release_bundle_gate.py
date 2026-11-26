"""The bundle gate and the release job that plans the bundle (PIPE-RELEASE-R020, R025.6)."""

from __future__ import annotations

import json
import sys
import unittest.mock as mock
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_scope as rs  # noqa: E402

BEHAVIOUR = "**Row.** Caller chain: x. | Test: `t.py::t` (L3). |"


def _rows() -> dict[str, dict]:
    def row(rid: str, repo: str, deps: list[str], status: str = "VERIFIED") -> dict:
        return {
            "id": rid,
            "repo": repo,
            "spec_id": "S",
            "family": "f",
            "depends_on": deps,
            "status": status,
            "text": BEHAVIOUR,
        }

    return {"S-R001": row("S-R001", "a", []), "S-R002": row("S-R002", "b", ["S-R001"], "LANDED")}


def _doc(rows: dict[str, dict]) -> dict:
    return rs.manifest("P1", list(rows), rows)


# spec: PIPE-RELEASE-R020
def test_bundle_with_open_rows_or_failed_scenario_stops() -> None:
    from scripts.release_plan import render_plan

    rows = _rows()
    doc = _doc(rows)
    plan = render_plan(doc, rows)
    reach = {"S-R001": True, "S-R002": True}
    passed = {doc["scenario"]: {"passed": True}}
    found = rs.bundle_gate(doc, rows, plan, passed, reach)
    assert found == ["BUNDLE_NOT_DELIVERED: S-R002: NOT_VERIFIED"]
    rows["S-R002"]["status"] = "VERIFIED"
    assert rs.bundle_gate(doc, rows, plan, passed, reach) == []
    failed = rs.bundle_gate(doc, rows, plan, {doc["scenario"]: {"passed": False}}, reach)
    assert failed[-1] == f"BUNDLE_NOT_DELIVERED: scenario {doc['scenario']} has no passing run"
    assert all("SCENARIO_NOT_PASSED" in f for f in failed[:-1])
    assert rs.bundle_gate(doc, rows, plan, passed, {"S-R001": True})  # an unreachable row stops it too


# spec: PIPE-RELEASE-R025.6
def test_release_job_stops_on_bundle_cycle(tmp_path: Path, capsys) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/release_bundle.yml").read_text(encoding="utf-8"))
    run = "\n".join(step["run"] for step in workflow["jobs"]["bundle"]["steps"] if "run" in step)
    assert "release_scope.py --workspace" in run and "--check" in run and "--plan" in run and "--gate" in run
    rows = _rows()
    rows["S-R001"]["depends_on"] = ["S-R002"]  # a depends on b and b on a
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / "P1.yml").write_text(json.dumps(_doc(rows)))
    with mock.patch.object(rs, "all_rows", return_value=rows):
        code = rs.main(["--workspace", str(tmp_path), "--releases", str(releases), "--plan", "P1", "--gate"])
    captured = capsys.readouterr()
    assert code == 1 and "BUNDLE_CYCLE" in captured.err and captured.out == ""
