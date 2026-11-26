"""The program exit gates table of the release plan (PIPE-RELEASE-R026.1 to R026.4)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_scope as rs  # noqa: E402

TABLE = """## Phase 1

### Program exit gates

| Gate | Owning rows | Phase | Plan section |
|---|---|---|---|
| Specs land | `A-X-R001`, `B-Y-R001` | P1 to P5 | here |
| Late | `B-Y-R001` | P5 | here |
"""
OWNERS = {"medulla", "arbora"}


def _rows() -> dict[str, dict]:
    return {
        "A-X-R001": {"repo": "medulla", "status": "VERIFIED", "text": "x Caller chain: y | `t` (L3). |"},
        "B-Y-R001": {"repo": "arbora", "status": "VERIFIED", "text": "x | `t`. |"},
    }


# spec: PIPE-RELEASE-R026.1
def test_gate_table_with_a_missing_row_or_phase_fails() -> None:
    assert rs.exit_gates(TABLE, _rows(), OWNERS) == []
    assert any("names no row" in p for p in rs.exit_gates(TABLE.replace("`B-Y-R001` | P5", " | P5"), _rows(), OWNERS))
    assert any("defined by no spec" in p for p in rs.exit_gates(TABLE.replace("B-Y-R001", "Z-Q-R009"), _rows(), OWNERS))
    assert any("outside P1 to P5" in p for p in rs.exit_gates(TABLE.replace("| P5 |", "| P6 |"), _rows(), OWNERS))
    assert any("owner map" in p for p in rs.exit_gates(TABLE, _rows(), {"medulla"}))
    assert rs.exit_gates("no table", _rows(), OWNERS)


# spec: PIPE-RELEASE-R026.2
def test_final_gate_lists_open_connector_rows_and_unready_services() -> None:
    rows = _rows()
    rows["C-Z-R001"] = {"repo": "conn", "status": "LANDED", "text": ""}
    rows["C-Z-R002"] = {"repo": "conn", "status": "VERIFIED", "text": "x Caller chain: y | `t` (L3). |"}
    report = {"connectors": {"alpha": {"ready": True}, "beta": {"ready": False}}}
    found = rs.connector_gate(rows, {"conn"}, {"C-Z-R002": True}, {"passed": True}, report)
    assert found == ["open row C-Z-R001: NOT_VERIFIED", "connector beta is not ready"]
    rows["C-Z-R001"]["status"] = "VERIFIED"
    rows["C-Z-R001"]["text"] = rows["C-Z-R002"]["text"]
    report["connectors"]["beta"]["ready"] = True
    assert rs.connector_gate(rows, {"conn"}, {"C-Z-R001": True, "C-Z-R002": True}, {"passed": True}, report) == []


# spec: PIPE-RELEASE-R026.3
def test_final_gate_needs_a_passing_run_for_each_channel() -> None:
    runs = {rs.FINAL_SCENARIO: {"channels": {"web": {"passed": True}, "messaging": {"passed": False}}}}
    assert rs.channel_gate(runs) == ["channel messaging has no passing run"]
    assert rs.channel_gate({}) == ["channel web has no passing run", "channel messaging has no passing run"]
    runs[rs.FINAL_SCENARIO]["channels"]["messaging"]["passed"] = True
    assert rs.channel_gate(runs) == []


def _fixture_repo(path: Path, ids: list[str]) -> None:
    import subprocess

    path.mkdir(parents=True)
    spec = path / "specs" / "core"
    spec.mkdir(parents=True)
    rows = "\n".join(f"| `{i}` | **Row {i}.** Behaviour. | Test: `t.py::t`. |" for i in ids)
    (spec / "requirements.md").write_text(
        f"# Requirements\n\n| ID | Requirement | Verification |\n|---|---|---|\n{rows}\n"
    )
    git = [
        "git",
        "-C",
        str(path),
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "--", "specs"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "specs"], check=True)
    subprocess.run([*git, "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)


# spec: PIPE-RELEASE-R026.4
def test_program_exit_gates_table_resolves_against_the_workspace(tmp_path: Path, capsys) -> None:
    plan = ROOT / "specs/ordered-digest-release/plan.md"
    gates = rs.gate_table(plan.read_text(encoding="utf-8"))
    assert len(gates) >= 12 and all(g["rows"] and g["phase"] for g in gates)
    owners = {"PIPE": "pipelines", "ARBORA": "arbora", "MEDULLA": "medulla"}
    by_repo: dict[str, list[str]] = {}
    for gate in gates:
        for rid in gate["rows"]:
            by_repo.setdefault(owners[rid.split("-")[0]], []).append(rid)
    for repo, ids in by_repo.items():
        _fixture_repo(tmp_path / "agent-packages" / repo, sorted(set(ids)))
    assert rs.main(["--workspace", str(tmp_path), "--exit-gates", "--plan-file", str(plan)]) == 0
    # The same fixture with one gate row removed from its owning spec fails and names the gate.
    victim = gates[0]["rows"][0]
    repo = tmp_path / "agent-packages" / owners[victim.split("-")[0]]
    _fixture_repo(
        tmp_path / "other" / "agent-packages" / owners[victim.split("-")[0]],
        [i for i in by_repo[owners[victim.split("-")[0]]] if i != victim],
    )
    for other in by_repo:
        if other != owners[victim.split("-")[0]]:
            _fixture_repo(tmp_path / "other" / "agent-packages" / other, sorted(set(by_repo[other])))
    capsys.readouterr()
    assert rs.main(["--workspace", str(tmp_path / "other"), "--exit-gates", "--plan-file", str(plan)]) == 1
    assert f"row {victim} is defined by no spec" in capsys.readouterr().err
    assert repo.exists()
