"""Organization view of delivery: aggregate over repositories and the page's delivery views."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import build as explorer  # noqa: E402
from scripts.architecture_explorer.delivery import aggregate  # noqa: E402

PKG = ROOT / "scripts/architecture_explorer"


def _row(rid: str, repo: str, status: str = "SPECIFIED", depends_on=(), family: str = "fam") -> dict:
    return {
        "id": rid,
        "title": f"title {rid}",
        "status": status,
        "repo": repo,
        "family": family,
        "spec_id": "FIX",
        "depends_on": list(depends_on),
    }


CQ = "MEDULLA-CQ-ORCH-R001"


def _fixture() -> list[dict]:
    return [
        _row("MEDULLA-A-R001", "epistemic-graph"),
        _row("AR-A-R001", "arbora", depends_on=["MEDULLA-A-R001"]),
        _row("AR-A-R002", "arbora", depends_on=["MEDULLA-A-R001", "NOWHERE-R001"]),
        _row("AR-A-R003", "arbora"),
        _row(CQ, "epistemic-graph", depends_on=["AR-A-R001"]),
    ]


# spec: PIPE-CONNSPEC-R016
def test_aggregate_over_repositories() -> None:
    got = aggregate(_fixture())
    assert got["scores"]["MEDULLA-A-R001"]["priority"] == 10 + 2 * 3
    assert got["scores"]["AR-A-R001"]["cqs"] == [CQ]
    assert got["frontier"][0] == "MEDULLA-A-R001" and "AR-A-R001" not in got["frontier"]
    assert got["unserved"] == ["AR-A-R002", "AR-A-R003"]
    assert [q["id"] for q in got["questions"]] == [CQ]
    assert [s["repo"] for s in got["bundles"][0]["steps"]] == ["epistemic-graph", "arbora"]


# spec: PIPE-CONNSPEC-R016
def test_page_embeds_delivery_views() -> None:
    template = (PKG / "template.html").read_text()
    for marker in (
        'id="vnext"',
        'id="vpath"',
        "Sort by priority",
        "Filter by competency question",
        "No CQ dependency path",
        "goalBadges",
    ):
        assert marker in template
    rows = _fixture()
    delivery = aggregate(rows)
    delivery["frontier_set"], delivery["unserved_set"] = set(delivery["frontier"]), set(delivery["unserved"])
    entry = explorer.spec_entry(rows[1], delivery)
    assert entry["priority"] == 10 + 2 and entry["cqs"] == [CQ]
    assert explorer.spec_entry(rows[3], delivery)["unserved"] is True
    block = explorer.page_delivery(delivery, rows)
    assert block["next"][0]["id"] == "MEDULLA-A-R001" and block["counts"]["unserved"] == 2


# spec: PIPE-CONNSPEC-R016
def test_cq_path_explanation_does_not_claim_missing_architecture_links() -> None:
    template = (PKG / "template.html").read_text()
    assert "CQ → Depends-on → requirement" in template
    assert "does not indicate missing architecture placement or implementation links" in template
    assert "not linked to a CQ" not in template
    assert "Not linked to a competency question" not in template
    rows = _fixture()
    rows.append(_row("TUIG-RUNTIME-R099", "agent-terminal-ui", depends_on=[CQ]))
    delivery = aggregate(rows)
    assert "TUIG-RUNTIME-R099" in delivery["unserved"]
    assert delivery["scores"]["TUIG-RUNTIME-R099"]["cqs"] == []
    assert delivery["scores"]["AR-A-R001"]["cqs"] == [CQ]
