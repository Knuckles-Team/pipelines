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
    scenarios = {"P1": ["A-X-R001"], "P2": ["A-X-R002", "A-X-R001"], "P3": [], "P4": ["D-W-R001"], "P5": []}
    assert rs.closure(["A-X-R001"], {k: v["depends_on"] for k, v in rows.items()}) == {
        "A-X-R001",
        "B-Y-R001",
        "C-Z-R001",
    }
    by_phase, missing = rs.assign(scenarios, rows)
    assert missing == []
    assert by_phase == {
        "P1": ["A-X-R001", "B-Y-R001", "C-Z-R001"],
        "P2": ["A-X-R002"],
        "P3": [],
        "P4": ["D-W-R001"],
        "P5": [],
    }
    manifests = [rs.manifest(p, ids, rows) for p, ids in by_phase.items()]
    assert manifests[0]["scenario"] == "ARBORA-ACCEPTANCE-R006.1"
    assert {"repo": "scion-sdk", "spec": "B-Y", "roots": ["B-Y-R001"]} in manifests[0]["scope"]
    assert manifests[-1]["rest"] == "all-remaining"
    assert rs.remaining_manifest()["scope"] == "all-remaining"
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
    assert docs[-1]["rest"] == "all-remaining"
    ids = [rid for d in docs for rid in rs.scoped_ids(d)]
    assert len(ids) == len(set(ids))
    assert [d["scenario"] for d in docs[:4]] == [f"ARBORA-ACCEPTANCE-R006.{n}" for n in (1, 2, 3, 4)]
    json.dumps(docs)


@pytest.mark.spec("PIPE-RELEASE-R023")
def test_p5_names_the_cross_source_scenario() -> None:
    assert rs.SCENARIOS["P5"][0] == "ARBORA-ACCEPTANCE-R006.7"
    docs = {d["id"]: d for d in rs.load_manifests(ROOT / "releases")}
    assert docs["P5"]["scenario"] == "ARBORA-ACCEPTANCE-R006.7"
    assert docs["P5"]["rest"] == "all-remaining"
    # The rows the scenario exercises join P5 unless an earlier phase holds them.
    rows = _rows()
    by_phase, _ = rs.assign({"P1": ["D-W-R001"], "P5": ["A-X-R001", "D-W-R001"]}, rows)
    assert by_phase["P1"] == ["D-W-R001"]
    assert by_phase["P5"] == ["A-X-R001", "B-Y-R001", "C-Z-R001"]


def _contract_rows() -> dict[str, dict]:
    rows = _rows()
    rows["E-V-R001"] = {"id": "E-V-R001", "repo": "overstory", "spec_id": "E-V", "family": "f", "depends_on": []}
    rows["A-X-R002"]["consumed_by"] = ["E-V-R001"]
    rows["E-V-R001"]["provided_by"] = ["A-X-R002"]
    return rows


@pytest.mark.spec("PIPE-RELEASE-R025.1")
def test_closure_follows_depends_on_and_contract_edges() -> None:
    rows = _contract_rows()
    plain = {k: v["depends_on"] for k, v in rows.items()}
    assert rs.closure(["A-X-R002"], plain) == {"A-X-R002", "C-Z-R001"}
    got = rs.closure(["A-X-R002"], rs.depends_map(rows))
    assert got == {"A-X-R002", "C-Z-R001", "E-V-R001"}  # the consumer repository's row joins through the contract
    assert rs.closure(["E-V-R001"], rs.depends_map(rows)) == got  # and the provider joins from the consumer


@pytest.mark.spec("PIPE-RELEASE-R025.2")
def test_train_order_is_topological_and_not_hard_coded() -> None:
    rows = _contract_rows()
    order = rs.train_order(set(rows), rows)
    assert order == ["meristem", "scion-sdk", "medulla", "overstory"]
    # Renaming every repository changes the order the same way: no name is written in code, ties sort by name.
    renamed = {
        k: {**v, "repo": {"meristem": "z3", "scion-sdk": "z2", "medulla": "z1", "overstory": "z0"}[v["repo"]]}
        for k, v in rows.items()
    }
    assert rs.train_order(set(renamed), renamed) == ["z3", "z2", "z1", "z0"]
    free = {"A": {"repo": "b", "depends_on": []}, "B": {"repo": "a", "depends_on": []}}
    assert rs.train_order({"A", "B"}, free) == ["a", "b"]


@pytest.mark.spec("PIPE-RELEASE-R025.3")
def test_cycle_across_bundles_refuses_with_bundle_cycle(tmp_path: Path, capsys) -> None:
    rows = _rows()
    rows["C-Z-R001"]["depends_on"] = ["A-X-R002"]  # meristem needs medulla, which needs meristem
    with pytest.raises(rs.BundleCycle) as raised:
        rs.train_order(set(rows), rows)
    assert str(raised.value).startswith("BUNDLE_CYCLE:")
    assert {"medulla", "meristem"} <= set(raised.value.repos) and {"A-X-R002", "C-Z-R001"} <= set(raised.value.rows)
    # main refuses with BUNDLE_CYCLE and exit 1 before it writes any file.
    releases = tmp_path / "releases"
    scenarios = {"P1": ["A-X-R002"], "P2": [], "P3": [], "P4": [], "P5": []}
    import unittest.mock as mock

    with (
        mock.patch.object(rs, "all_rows", return_value=rows),
        mock.patch.object(rs, "read_scenarios", return_value=scenarios),
    ):
        assert rs.main(["--workspace", str(tmp_path), "--releases", str(releases)]) == 1
    assert "BUNDLE_CYCLE" in capsys.readouterr().err and not releases.exists()
