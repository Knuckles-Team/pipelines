"""Release bundle manifests: scenario scope, dependency closure and one release per row (PIPE-RELEASE-R021)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_scope as rs  # noqa: E402


def _rows() -> dict[str, dict]:
    def r(rid: str, repo: str, deps: list[str]) -> dict:
        return {"id": rid, "repo": repo, "spec_id": rid.rsplit("-R", 1)[0], "family": "f", "depends_on": deps}

    return {
        "A-X-R001": r("A-X-R001", "medulla", ["B-Y-R001"]),
        "B-Y-R001": r("B-Y-R001", "scion-sdk", ["C-Z-R001"]),
        "C-Z-R001": r("C-Z-R001", "meristem", []),
        "A-X-R002": r("A-X-R002", "medulla", ["C-Z-R001"]),
        "D-W-R001": r("D-W-R001", "medulla", []),
    }


@pytest.mark.spec("PIPE-RELEASE-R021")
def test_scope_closure_and_single_release_per_row() -> None:
    rows = _rows()
    scenarios = {"P1": ["A-X-R001"], "P2": ["A-X-R002", "A-X-R001"], "P3": [], "P4": ["D-W-R001"]}
    assert rs.closure(["A-X-R001"], {k: v["depends_on"] for k, v in rows.items()}) == {
        "A-X-R001",
        "B-Y-R001",
        "C-Z-R001",
    }
    by_phase, missing = rs.assign(scenarios, rows)
    assert missing == []
    assert by_phase == {"P1": ["A-X-R001", "B-Y-R001", "C-Z-R001"], "P2": ["A-X-R002"], "P3": [], "P4": ["D-W-R001"]}
    manifests = [rs.manifest(p, ids, rows) for p, ids in by_phase.items()] + [rs.remaining_manifest()]
    assert manifests[0]["scenario"] == "ARBORA-ACCEPTANCE-R006.1"
    assert {"repo": "scion-sdk", "spec": "B-Y", "roots": ["B-Y-R001"]} in manifests[0]["scope"]
    assert manifests[-1]["scope"] == "all-remaining"
    assert rs.check(manifests, rows) == []
    # A row in two releases, and a row no repository declares, both fail the check.
    manifests[1]["scope"].append({"repo": "medulla", "spec": "A-X", "roots": ["A-X-R001", "A-X-R999"]})
    problems = rs.check(manifests, rows)
    assert any("A-X-R001: in both P1 and P2" in p for p in problems)
    assert any("A-X-R999" in p and "not declared" in p for p in problems)


@pytest.mark.spec("PIPE-RELEASE-R021")
def test_manifests_name_phase_scenario_and_scope_and_no_row_repeats() -> None:
    docs = rs.load_manifests(ROOT / "releases")
    assert [d["id"] for d in docs] == ["P1", "P2", "P3", "P4", "P5"]
    assert all({"id", "name", "phase", "scenario", "scope"} <= d.keys() for d in docs)
    assert docs[-1]["scope"] == "all-remaining"
    ids = [rid for d in docs for rid in rs.scoped_ids(d)]
    assert len(ids) == len(set(ids))
    assert [d["scenario"] for d in docs[:4]] == [f"ARBORA-ACCEPTANCE-R006.{n}" for n in (1, 2, 3, 4)]
    json.dumps(docs)
