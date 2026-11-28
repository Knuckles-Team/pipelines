"""Canopy row drawer: the detail record of one row (PIPE-PAGES-R053)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import delivery as delivery_mod  # noqa: E402
from scripts.architecture_explorer import details  # noqa: E402
from canopy_browser import NEEDS_BROWSER, PREFIX, build_site, drive, serve  # noqa: E402

PLAN = "# FAM - Plan\n\n## Summary\n\nThe solver handles FAM-R001 first.\n\nUnrelated paragraph.\n\nFAM-R001.1 is a child.\n"
TASKS = "# Tasks\n\n- [x] T001 FAM-R001 write the solver\n- [ ] T002 FAM-R001 prove it\n- [ ] T003 FAM-R002 other\n"
CHECK = "# Checklist\n\n- [x] FAM-R001 has a test\n- [ ] FAM-R002 has a test\n"
DOCS = {"plan.md": PLAN, "tasks.md": TASKS, "checklists/req.md": CHECK, "spec.md": "# FAM\n\nNothing here.\n"}


def _drawer(row_id: str, docs=DOCS, delivery=None) -> dict:
    return details.row_drawer(docs, row_id, details.Ctx("pipelines", "fam"), delivery, set(), "fam")


@pytest.mark.spec("PIPE-PAGES-R053.1")
def test_row_drawer_model_has_excerpts_tasks_checklist_and_unblocks() -> None:
    rows = [
        {"id": "FAM-R001", "repo": "pipelines", "status": "SPECIFIED", "family": "fam", "depends_on": []},
        {"id": "FAM-R002", "repo": "pipelines", "status": "SPECIFIED", "family": "fam", "depends_on": ["FAM-R001"]},
        {"id": "FAM-R003", "repo": "pipelines", "status": "VERIFIED", "family": "fam", "depends_on": ["FAM-R001"]},
    ]
    agg = delivery_mod.aggregate(rows)
    assert agg["dependents"] == {"FAM-R001": ["FAM-R002"]}  # only open rows are unblocked
    drawer = _drawer("FAM-R001", delivery=agg)
    assert set(drawer) == {
        "excerpts",
        "none",
        "tasks",
        "progress",
        "checklist",
        "unblocks",
        "cqs",
        "priority",
        "questions",
    }
    assert drawer["unblocks"] == ["FAM-R002"] and drawer["priority"] == agg["scores"]["FAM-R001"]["priority"]
    assert drawer["tasks"] == [
        {"done": True, "text": "T001 FAM-R001 write the solver"},
        {"done": False, "text": "T002 FAM-R001 prove it"},
    ]
    assert drawer["progress"] == [1, 2]
    assert drawer["checklist"] == [{"done": True, "text": "FAM-R001 has a test"}]
    assert all(len(html) <= details.EXCERPT_MAX for html in drawer["excerpts"].values())


@pytest.mark.spec("PIPE-PAGES-R053.2")
def test_excerpts_hold_only_paragraphs_that_name_the_row() -> None:
    drawer = _drawer("FAM-R001")
    plan = drawer["excerpts"]["plan"]
    assert "solver handles FAM-R001" in plan and "Unrelated" not in plan and "child" not in plan  # not the longer ID
    assert drawer["excerpts"]["spec"] == "" and "spec" in drawer["none"] and "plan" not in drawer["none"]
    assert drawer["none"] == ["spec", "test-spec"]
    # A row with no match anywhere has an empty excerpt and the none marker for every kind.
    empty = _drawer("FAM-R404")
    assert set(empty["none"]) == {"spec", "plan", "test-spec", "checklists"} and not any(empty["excerpts"].values())
    assert empty["tasks"] == [] and empty["progress"] == [0, 0]
    # A very long paragraph is cut so the rendered HTML stays within the limit; raw HTML is escaped.
    big = {"plan.md": "FAM-R001 <script>x</script> " + "word " * 600}
    out = _drawer("FAM-R001", big)["excerpts"]["plan"]
    assert 0 < len(out) <= details.EXCERPT_MAX and "<script>" not in out


R030 = f"{PREFIX}-R030"
OPEN_ROW = f"""
const id="{R030}", h=window.__arch.search(id)[0];
window.__arch.go(h.node,{{hit:true,open:true,instant:true}});
await new Promise(r=>setTimeout(r,700));
const btn=()=>document.querySelector('[data-spec="'+id+'"] .dr');
"""


def _run(monkeypatch, tmp_path: Path, script: str) -> dict:
    site = build_site(monkeypatch, tmp_path)
    with serve(site) as url:
        return drive(tmp_path, url, script)


@pytest.mark.spec("PIPE-PAGES-R053.3")
@pytest.mark.browser
@NEEDS_BROWSER
def test_a_row_click_opens_the_drawer_and_sets_the_row_hash(monkeypatch, tmp_path: Path) -> None:
    out = _run(
        monkeypatch,
        tmp_path,
        OPEN_ROW
        + """
btn().click(); await new Promise(r=>setTimeout(r,600));
const d=document.getElementById("drawer"), opened={hidden:d.hidden, hash:location.hash, heading:document.getElementById("drawer-h").textContent, focus:document.activeElement.id, labelled:d.getAttribute("aria-labelledby")};
document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));
const closed={hidden:d.hidden, focusIsRowButton:document.activeElement===btn(), hash:location.hash};
return {opened,closed};
""",
    )
    assert out["opened"]["hash"].endswith(f"row={R030}") and out["opened"]["heading"] == R030
    assert out["opened"]["labelled"] == "drawer-h"
    assert out["opened"]["hidden"] is False and out["opened"]["focus"] == "drawer-h"
    assert (
        out["closed"]["hidden"] is True
        and out["closed"]["focusIsRowButton"] is True
        and "row=" not in out["closed"]["hash"]
    )


@pytest.mark.spec("PIPE-PAGES-R053.4")
@pytest.mark.browser
@NEEDS_BROWSER
def test_missing_row_and_failed_family_load_are_reported_in_the_drawer(monkeypatch, tmp_path: Path) -> None:
    out = _run(
        monkeypatch,
        tmp_path,
        OPEN_ROW
        + """
const before=window.__arch.selected;
window.__arch.openDrawer("NOPE-R999",true);
const missing={heading:document.getElementById("drawer-h").textContent, text:document.getElementById("drawer").textContent, selected:window.__arch.selected===before};
window.fetch=()=>Promise.reject(new Error("offline"));
btn().click(); await new Promise(r=>setTimeout(r,500));
const d=document.getElementById("drawer"), failed={alert:!!d.querySelector('[role="alert"]'), retry:!!Array.from(d.querySelectorAll("button")).find(b=>b.textContent==="Retry"), family:d.textContent.includes("scion-connector-control")};
const inert=document.getElementById("drawer").querySelectorAll("script,img,iframe").length;
return {missing,failed,inert};
""",
    )
    assert out["missing"]["heading"] == "Row not found" and "Row not found: NOPE-R999" in out["missing"]["text"]
    assert out["missing"]["selected"] is True
    assert out["failed"] == {"alert": True, "retry": True, "family": True} and out["inert"] == 0


@pytest.mark.spec("PIPE-PAGES-R053.5")
@pytest.mark.browser
@NEEDS_BROWSER
def test_drawer_lists_exact_paths_and_evidence_links(monkeypatch, tmp_path: Path) -> None:
    out = _run(
        monkeypatch,
        tmp_path,
        OPEN_ROW
        + """
btn().click(); await new Promise(r=>setTimeout(r,600));
const d=document.getElementById("drawer");
return {paths:Array.from(d.querySelectorAll(".files code")).map(c=>c.textContent), links:Array.from(d.querySelectorAll(".files a")).map(a=>a.href), state:d.querySelector(".badge").textContent};
""",
    )
    base = "specs/scion-connector-control/"
    assert f"{base}spec.md" in out["paths"] and f"{base}plan.md" in out["paths"]
    assert all(link.startswith("https://github.com/Knuckles-Team/scion-sdk/blob/HEAD/specs/") for link in out["links"])
    assert out["state"] == "SPECIFIED"


@pytest.mark.spec("PIPE-PAGES-R053.6")
@pytest.mark.browser
@NEEDS_BROWSER
def test_the_drawer_opens_in_a_browser_with_tasks_and_unblocks(monkeypatch, tmp_path: Path) -> None:
    out = _run(
        monkeypatch,
        tmp_path,
        OPEN_ROW
        + """
btn().click(); await new Promise(r=>setTimeout(r,600));
const d=document.getElementById("drawer");
return {text:d.textContent, unblocks:Array.from(d.querySelectorAll(".unblocks a")).map(a=>a.textContent)};
""",
    )
    assert "must hold" in out["text"] and "1 of 2 tasks" in out["text"]
    assert sorted(out["unblocks"]) == ["CONN-ADGUARD-HOME-AGENT-R002", f"{PREFIX}-R043"]
