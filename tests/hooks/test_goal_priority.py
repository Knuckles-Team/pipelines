"""Competency-question priority: Depends-on parsing, formula, frontier, unserved, release bundles."""

from __future__ import annotations

import json

from pipelines_hooks.specs.priority import Node, bundles, frontier, score, unserved
from pipelines_hooks.specs.requirements_doc import parse_rows
from tests.hooks.conftest import Repo


# spec: PIPE-CONNSPEC-R012
def test_row_depends_on_parses() -> None:
    text = "| `A-R001` | **T.** Text. Depends-on: B-R002, C-R003.1. More text | v |\n"
    (row,) = parse_rows(text)
    assert row.depends_on == ("B-R002", "C-R003.1")
    assert parse_rows("| `A-R002` | **T.** no declaration | v |\n")[0].depends_on == ()


# spec: PIPE-CONNSPEC-R012
def test_prose_dependency_forms_resolve_relative_and_full_ids() -> None:
    text = (
        "| `EG-SUPPLY-VOCAB-R001.4` | **T.** Depends on `R001.1`, `.2` and `EG-OTHER-R005`. Requires `R002`. "
        "After a while. After `ARB-X-R010.3`. | v |\n"
        "| `EG-SUPPLY-VOCAB-R002` | **T.** Depends on EG-FOO-R004 and ARB-BAR-R009.2. Requires linking a to b. | v |\n"
        "| `EG-SUPPLY-VOCAB-R003` | **T.** Depends on `.1`. | v |\n"
    )
    rows = {r.id: r.depends_on for r in parse_rows(text)}
    assert rows["EG-SUPPLY-VOCAB-R001.4"] == (
        "EG-SUPPLY-VOCAB-R001.1",  # relative to the spec prefix
        "EG-SUPPLY-VOCAB-R001.2",  # `.2` is a sibling of a child row
        "EG-OTHER-R005",  # full, cross-spec
        "EG-SUPPLY-VOCAB-R002",
        "ARB-X-R010.3",  # "After" with a backticked ID; "After a while" adds nothing
    )
    assert rows["EG-SUPPLY-VOCAB-R002"] == (
        "EG-FOO-R004",
        "ARB-BAR-R009.2",
    )  # bare full IDs; "Requires linking" adds nothing
    assert rows["EG-SUPPLY-VOCAB-R003"] == ("EG-SUPPLY-VOCAB-R003.1",)  # `.1` is a child of a top-level row


def _graph() -> dict[str, Node]:
    cq1, cq2 = "EG-CQ-ORCH-R001", "EG-CQ-ORCH-R002"
    return {
        cq1: Node(cq1, "epistemic-graph", "SPECIFIED", ("ARB-R1",)),
        cq2: Node(cq2, "epistemic-graph", "VERIFIED", ("SDK-R1",)),
        "EG-R1": Node("EG-R1", "epistemic-graph", "SPECIFIED", ()),
        "SDK-R1": Node("SDK-R1", "agent-connector-sdk", "SPECIFIED", ("EG-R1",)),
        "ARB-R1": Node("ARB-R1", "arbora", "SPECIFIED", ("SDK-R1", "EG-R1")),
        "DONE-R1": Node("DONE-R1", "arbora", "VERIFIED", ()),
        "GATE-R1": Node("GATE-R1", "pipelines", "SPECIFIED", ("DONE-R1",), functional=False),
        "BARE-R1": Node("BARE-R1", "pipelines", "SPECIFIED", ()),
        "CONN-R1": Node("CONN-R1", "gitlab-api", "SPECIFIED", ("SDK-R1",)),
    }


# spec: PIPE-CONNSPEC-R013
def test_priority_formula() -> None:
    got = score(_graph())
    # EG-R1: reached by both CQs (open and done count), unblocks SDK-R1, ARB-R1, CONN-R1, and the open CQ-1: 10*2 + 2*4
    assert got["EG-R1"]["priority"] == 28
    assert got["EG-R1"]["cqs"] == ["EG-CQ-ORCH-R001", "EG-CQ-ORCH-R002"]
    # SDK-R1: both CQs; unblocks ARB-R1, CONN-R1, CQ-1: 20 + 6
    assert got["SDK-R1"]["priority"] == 26
    # ARB-R1: only CQ-1 reaches it; unblocks CQ-1: 10 + 2
    assert got["ARB-R1"]["priority"] == 12
    assert got["BARE-R1"]["priority"] == 0
    assert got["GATE-R1"]["priority"] == 0
    assert "DONE-R1" not in got
    halved = {
        "N": Node("N", "r", "SPECIFIED", ()),
        "Q": Node("Q", "r", "SPECIFIED", ("N",)),
        "EG-CQ-X-R001": Node("EG-CQ-X-R001", "r", "VERIFIED", ("N",), functional=True),
    }
    assert score(halved)["N"]["priority"] == 10 + 2
    halved["N"] = halved["N"]._replace(functional=False)
    assert score(halved)["N"]["priority"] == 6


# spec: PIPE-CONNSPEC-R014
def test_frontier_and_unserved() -> None:
    nodes = _graph()
    assert frontier(nodes) == ["BARE-R1", "EG-R1", "GATE-R1"]
    assert unserved(nodes, score(nodes)) == ["BARE-R1", "CONN-R1"]


# spec: PIPE-CONNSPEC-R014
def test_generator_writes_priority_frontier_unserved(repo: Repo) -> None:
    rows = (
        "# demo\n\n| ID | Requirement |\n|---|---|\n"
        "| `TEST-R001` | **First.** |\n"
        "| `TEST-R002` | **Second.** Depends-on: TEST-R001. |\n"
        "| `TEST-R003` | **Question.** Depends-on: TEST-R002. |\n"
        "| `TEST-R004` | **Untouched.** |\n"
    )
    repo.commit({"specs/demo/requirements.md": rows}, "add spec")
    assert repo.run("spec-status", "--write") == 0
    doc = json.loads((repo.root / "specs/demo/status.json").read_text())
    by_id = {r["id"]: r for r in doc["requirements"]}
    assert by_id["TEST-R001"]["priority"] == 4  # unblocks TEST-R002 and TEST-R003
    assert by_id["TEST-R002"]["priority"] == 2
    assert by_id["TEST-R002"]["depends_on"] == ["TEST-R001"]
    assert doc["frontier"] == ["TEST-R001", "TEST-R004"]
    assert doc["unserved"] == ["TEST-R001", "TEST-R002", "TEST-R003", "TEST-R004"]


# spec: PIPE-CONNSPEC-R015
def test_bundle_orders_steps_by_release_train() -> None:
    nodes = _graph()
    got = bundles(nodes, score(nodes))
    assert len(got) == 1  # GATE-R1 and BARE-R1 have no cross-repository edge
    bundle = got[0]
    assert bundle["priority"] == 28
    assert [s["repo"] for s in bundle["steps"]] == ["epistemic-graph", "agent-connector-sdk", "arbora", "gitlab-api"]
    first = bundle["steps"][0]["rows"][0]
    assert first["id"] == "EG-R1" and first["unblocks"] == ["ARB-R1", "CONN-R1", "EG-CQ-ORCH-R001", "SDK-R1"]
