"""Small fixture-tree tests for the deterministic spec dependency/sizing tool.

Each fixture is a hand-built, self-contained ``specs/<name>/`` tree under
``tmp_path`` -- never a reference into a sibling repository checkout, so these
tests carry no dependency on anything outside this repository.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.spec_graph import (
    apply_split,
    dependency_edges,
    frontier,
    load_repo,
    load_repos,
    needs_split,
    proposed_splits,
    size_score,
)


def _status(spec_id: str, owner_repo: str, requirements: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "spec_id": spec_id,
        "owner_repo": owner_repo,
        "requirement_ids": [entry["id"] for entry in requirements],
        "delivery_state": "SPECIFIED",
        "acceptance_state": "NOT_AUDITED",
        "evidence": [],
        "requirements": requirements,
    }


def _entry(rid: str, state: str = "SPECIFIED", title: str | None = None) -> dict:
    return {"id": rid, "title": title or rid, "delivery_state": state, "evidence": []}


_STUB_CHECKER = '''"""Minimal stand-in for a repository's real check_public_specs.py, used only
by tests/test_spec_graph.py so apply_split's self-validation call has
something to run against a tiny fixture tree."""
import json


def problems(root):
    errors = []
    for spec_dir in (root / "specs").iterdir():
        if not spec_dir.is_dir():
            continue
        status = json.loads((spec_dir / "status.json").read_text(encoding="utf-8"))
        ids = status.get("requirement_ids", [])
        entries = status.get("requirements", [])
        if [entry.get("id") for entry in entries] != ids:
            errors.append(f"{spec_dir}: requirements must match requirement_ids in order")
        defined = (spec_dir / "requirements.md").read_text(encoding="utf-8")
        for rid in ids:
            if f"`{rid}`" not in defined:
                errors.append(f"{spec_dir}: {rid} missing from requirements.md")
    return errors
'''


def _write_spec(
    root: Path,
    repo: str,
    spec: str,
    *,
    status: dict,
    requirements_md: str = "",
    tasks_md: str = "",
    spec_md: str = "",
    test_spec_md: str = "",
) -> None:
    spec_dir = root / repo / "specs" / spec
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    (spec_dir / "requirements.md").write_text(requirements_md, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks_md, encoding="utf-8")
    (spec_dir / "spec.md").write_text(spec_md, encoding="utf-8")
    (spec_dir / "test-spec.md").write_text(test_spec_md, encoding="utf-8")
    scripts_dir = root / repo / "scripts"
    checker = scripts_dir / "check_public_specs.py"
    if not checker.is_file():
        scripts_dir.mkdir(parents=True, exist_ok=True)
        checker.write_text(_STUB_CHECKER, encoding="utf-8")


def test_requirements_md_row_names_a_dependency_and_ignores_a_look_alike(
    tmp_path: Path,
) -> None:
    status = _status("X-DEMO", "demo", [_entry("X-DEMO-R001"), _entry("X-DEMO-R002")])
    requirements_md = (
        "# X-DEMO requirements\n\n"
        "| ID | Requirement | Verification |\n"
        "|---|---|---|\n"
        "| `X-DEMO-R001` | First. | Checked by case X-T-01. |\n"
        "| `X-DEMO-R002` | Needs `X-DEMO-R001` and mentions itself, X-DEMO-R002. | Plain. |\n"
    )
    _write_spec(
        tmp_path, "demo", "x-demo", status=status, requirements_md=requirements_md
    )
    reqs = load_repo(tmp_path / "demo")
    assert reqs["X-DEMO-R002"].depends_on == {"X-DEMO-R001"}
    # X-T-01 looks like an ID but is never a declared requirement_id anywhere,
    # so it must not leak into the dependency graph.
    assert reqs["X-DEMO-R001"].depends_on == set()
    assert dependency_edges(reqs) == [("X-DEMO-R002", "X-DEMO-R001")]


def test_tasks_md_bold_id_names_a_dependency_and_counts_unchecked_lines(
    tmp_path: Path,
) -> None:
    status = _status("X-DEMO", "demo", [_entry("X-DEMO-R001"), _entry("X-DEMO-R002")])
    tasks_md = (
        "## Task list\n\n"
        "- [ ] **X-DEMO-R002:** Needs X-DEMO-R001 done first.\n"
        "- [x] **X-DEMO-R001:** Already landed.\n"
        "- [ ] Generic task naming X-DEMO-R001 again.\n"
    )
    _write_spec(tmp_path, "demo", "x-demo", status=status, tasks_md=tasks_md)
    reqs = load_repo(tmp_path / "demo")
    assert reqs["X-DEMO-R002"].depends_on == {"X-DEMO-R001"}
    # Any unchecked line that NAMES a requirement counts for it, regardless of
    # whether that ID is the line's bold "primary": line 1 names both R002
    # (bold) and R001 (plain), so both get a point from it; line 2 is checked
    # (not counted); line 3 names R001 again.
    assert reqs["X-DEMO-R002"].unchecked_tasks == 1
    assert reqs["X-DEMO-R001"].unchecked_tasks == 2


def test_cross_repo_heading_section_creates_a_cross_repo_edge(tmp_path: Path) -> None:
    producer_status = _status("EG-DEMO", "epistemic-graph", [_entry("EG-DEMO-R010")])
    producer_spec_md = (
        "# EG-DEMO\n\n"
        "## Acceptance boundary\n\n"
        "### Shared facts (EG-DEMO-R010)\n\n"
        "The consumer contract is AU-DEMO-R001 in agent-utilities.\n"
    )
    consumer_status = _status("AU-DEMO", "agent-utilities", [_entry("AU-DEMO-R001")])
    _write_spec(
        tmp_path,
        "epistemic-graph",
        "eg-demo",
        status=producer_status,
        spec_md=producer_spec_md,
    )
    _write_spec(tmp_path, "agent-utilities", "au-demo", status=consumer_status)
    reqs = load_repos([tmp_path / "epistemic-graph", tmp_path / "agent-utilities"])
    assert reqs["EG-DEMO-R010"].depends_on == {"AU-DEMO-R001"}
    edges = dependency_edges(reqs)
    assert ("EG-DEMO-R010", "AU-DEMO-R001") in edges


def test_frontier_orders_by_dependents_then_score(tmp_path: Path) -> None:
    # R002, R003 and R004 all name R001 as a dependency (three transitive
    # dependents, counted regardless of the dependent's own delivery state);
    # R004 itself is already LANDED so it never appears in the open frontier.
    status = _status(
        "X-DEMO",
        "demo",
        [
            _entry("X-DEMO-R001"),
            _entry("X-DEMO-R002"),
            _entry("X-DEMO-R003"),
            _entry("X-DEMO-R004", state="LANDED"),
        ],
    )
    requirements_md = (
        "| ID | Requirement | Verification |\n"
        "|---|---|---|\n"
        "| `X-DEMO-R001` | Base. | Check. |\n"
        "| `X-DEMO-R002` | Needs `X-DEMO-R001`. | Check. |\n"
        "| `X-DEMO-R003` | Needs `X-DEMO-R001`. | Check. |\n"
        "| `X-DEMO-R004` | Needs `X-DEMO-R001`. | Check. |\n"
    )
    _write_spec(
        tmp_path, "demo", "x-demo", status=status, requirements_md=requirements_md
    )
    reqs = load_repo(tmp_path / "demo")
    rows = frontier(reqs)["demo"]
    assert [row["id"] for row in rows[:1]] == ["X-DEMO-R001"]
    assert rows[0]["dependents"] == 3
    # R002/R003 are blocked (their dependency R001 is not LANDED), so only
    # R001 is in the unblocked frontier.
    assert [row["id"] for row in rows] == ["X-DEMO-R001"]


def test_size_score_matches_the_published_point_table(tmp_path: Path) -> None:
    status = _status(
        "X-DEMO",
        "demo",
        [_entry("X-DEMO-R001"), _entry("X-DEMO-R002", state="SPECIFIED")],
    )
    requirements_md = (
        "| ID | Requirement | Verification |\n"
        "|---|---|---|\n"
        "| `X-DEMO-R001` | Uses `pkg/a` and `pkg/b` and agent-webui, needs `X-DEMO-R002`."
        " | First clause. Second clause. |\n"
        "| `X-DEMO-R002` | Other. | Check. |\n"
    )
    tasks_md = "- [ ] First task for X-DEMO-R001.\n- [ ] Second task for X-DEMO-R001.\n"
    _write_spec(
        tmp_path,
        "demo",
        "x-demo",
        status=status,
        requirements_md=requirements_md,
        tasks_md=tasks_md,
    )
    reqs = load_repo(tmp_path / "demo")
    req = reqs["X-DEMO-R001"]
    delivery_states = {rid: r.delivery_state for rid, r in reqs.items()}
    # 2 unchecked tasks (+2) + 2 verification clauses (+2)
    # + 1 extra code root beyond the first (2 roots -> (2-1)*2 = +2)
    # + 1 other repo named (agent-webui) (+3)
    # + 1 unresolved dependency, X-DEMO-R002 is SPECIFIED not LANDED (+2)
    # = 11
    assert size_score(req, delivery_states) == 11
    assert needs_split(req, size_score(req, delivery_states))


def test_split_basis_prefers_code_roots_then_repo_then_fallback(tmp_path: Path) -> None:
    status = _status(
        "X-DEMO",
        "demo",
        [_entry("X-DEMO-R001"), _entry("X-DEMO-R002"), _entry("X-DEMO-R003")],
    )
    requirements_md = (
        "| ID | Requirement | Verification |\n"
        "|---|---|---|\n"
        "| `X-DEMO-R001` | Uses `pkg/a`, `pkg/b` and `pkg/c`, one clause, two,"
        " three, four, five, six, seven. | Check. |\n"
        "| `X-DEMO-R002` | Cross-repo with agent-webui, one clause, two,"
        " three, four, five, six, seven. | Check. |\n"
        "| `X-DEMO-R003` | No code root or other repo named."
        " | one. two. three. four. five. six. seven. |\n"
    )
    tasks_md = (
        "- [ ] a X-DEMO-R003.\n- [ ] b X-DEMO-R003.\n- [ ] c X-DEMO-R003.\n"
        "- [ ] d X-DEMO-R003.\n- [ ] e X-DEMO-R003.\n"
    )
    _write_spec(
        tmp_path,
        "demo",
        "x-demo",
        status=status,
        requirements_md=requirements_md,
        tasks_md=tasks_md,
    )
    reqs = load_repo(tmp_path / "demo")
    splits = {entry["id"]: entry for entry in proposed_splits(reqs)}
    assert splits["X-DEMO-R001"]["basis"] == "code_root"
    assert [c["scope"] for c in splits["X-DEMO-R001"]["children"]] == [
        "pkg/a",
        "pkg/b",
        "pkg/c",
    ]
    assert splits["X-DEMO-R002"]["basis"] == "repo"
    assert [c["scope"] for c in splits["X-DEMO-R002"]["children"]] == [
        "demo",
        "agent-webui",
    ]
    assert splits["X-DEMO-R003"]["basis"] == "fallback"
    assert [c["id"] for c in splits["X-DEMO-R003"]["children"]] == [
        "X-DEMO-R003.1",
        "X-DEMO-R003.2",
    ]


def test_write_applies_one_split_with_child_ids_and_depends_on(tmp_path: Path) -> None:
    status = _status("X-DEMO", "demo", [_entry("X-DEMO-R001"), _entry("X-DEMO-R999")])
    requirements_md = (
        "| ID | Requirement | Verification |\n"
        "|---|---|---|\n"
        "| `X-DEMO-R001` | Needs `X-DEMO-R999` and uses `pkg/a` and `pkg/b`,"
        " one. two. three. four. five. six. | Check. |\n"
        "| `X-DEMO-R999` | Other. | Check. |\n"
    )
    tasks_md = "## Task list\n\n- [ ] First task for X-DEMO-R001.\n- [ ] Second for X-DEMO-R001.\n"
    _write_spec(
        tmp_path,
        "demo",
        "x-demo",
        status=status,
        requirements_md=requirements_md,
        tasks_md=tasks_md,
    )
    repo_root = tmp_path / "demo"
    child_ids = apply_split(repo_root, "X-DEMO-R001")
    assert child_ids == ["X-DEMO-R001.1", "X-DEMO-R001.2"]

    spec_dir = repo_root / "specs" / "x-demo"
    requirements_text = (spec_dir / "requirements.md").read_text(encoding="utf-8")
    assert "`X-DEMO-R001.1`" in requirements_text
    assert "`X-DEMO-R001.2`" in requirements_text

    data = json.loads((spec_dir / "status.json").read_text(encoding="utf-8"))
    assert data["requirement_ids"] == [
        "X-DEMO-R001",
        "X-DEMO-R001.1",
        "X-DEMO-R001.2",
        "X-DEMO-R999",
    ]
    entries = {entry["id"]: entry for entry in data["requirements"]}
    assert [entry["id"] for entry in data["requirements"]] == data["requirement_ids"]
    assert entries["X-DEMO-R001"]["rollup"] is True
    assert entries["X-DEMO-R001"]["children"] == child_ids
    assert entries["X-DEMO-R001.1"]["delivery_state"] == "SPECIFIED"
    # Producer before consumer: the parent's own unresolved dependency carries
    # onto the first child, and each later child chains onto the one before it.
    assert entries["X-DEMO-R001.1"]["depends_on"] == ["X-DEMO-R999"]
    assert entries["X-DEMO-R001.2"]["depends_on"] == ["X-DEMO-R001.1"]

    tasks_text = (spec_dir / "tasks.md").read_text(encoding="utf-8")
    assert "X-DEMO-R001.1" in tasks_text
    assert "X-DEMO-R001.2" in tasks_text


def test_write_refuses_a_requirement_under_the_threshold(tmp_path: Path) -> None:
    status = _status("X-DEMO", "demo", [_entry("X-DEMO-R001")])
    requirements_md = (
        "| ID | Requirement | Verification |\n|---|---|---|\n"
        "| `X-DEMO-R001` | Small. | Check. |\n"
    )
    _write_spec(
        tmp_path, "demo", "x-demo", status=status, requirements_md=requirements_md
    )
    try:
        apply_split(tmp_path / "demo", "X-DEMO-R001")
        raised = False
    except SystemExit:
        raised = True
    assert raised
