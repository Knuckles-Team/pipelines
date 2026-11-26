"""Canopy diagram modes: the SDD phase of a spec family (PIPE-PAGES-R054)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import sdd  # noqa: E402
from scripts.architecture_explorer.sdd import SddPhase  # noqa: E402
from canopy_browser import ADGUARD, NEEDS_BROWSER, NEEDS_LAYOUT, PKG, PREFIX, build_site, drive, node_of, payload, serve  # noqa: E402

SPEC = "# FAM - Fam\n\n## Purpose\n\nWhy.\n"
TASKS_OPEN = "# Tasks\n\n- [ ] T001 FAM-R001 do it\n- [ ] T002 FAM-R002 do it\n"
TASKS_STARTED = "# Tasks\n\n- [x] T001 FAM-R001 do it\n- [ ] T002 FAM-R002 do it\n"


def _rows(*states: str) -> list[dict]:
    return [{"id": f"FAM-R00{i}", "status": s} for i, s in enumerate(states, 1)]


@pytest.mark.spec("PIPE-PAGES-R054.1")
def test_sdd_phase_enum_orders_six_phases() -> None:
    assert [p.label for p in SddPhase] == [
        "specified",
        "research-done",
        "plan-accepted",
        "tasks-ready",
        "implementing",
        "verified",
    ]
    assert list(SddPhase) == sorted(SddPhase) and set(sdd.PHASE_PREDICATES) == set(SddPhase)
    card = sdd.family_card({"spec.md": SPEC}, set(), "fam", [], _rows("SPECIFIED"))
    assert card["s"] == int(SddPhase.RESEARCH_DONE)
    assert sdd.family_card({}, set(), "fam", [], _rows("SPECIFIED"))["s"] == 0


@pytest.mark.spec("PIPE-PAGES-R054.2")
def test_each_phase_predicate_holds_only_on_its_artifacts() -> None:
    clean = lambda text: []  # noqa: E731
    broken = lambda text: ["1: missing heading"]  # noqa: E731
    rows = _rows("SPECIFIED", "SPECIFIED")

    def phase(docs, rows=rows, check=clean):
        return sdd.sdd_phase(docs, rows, check(docs.get("plan.md", "")) if docs.get("plan.md") else None)

    assert sdd.sdd_phase({}, rows) is None
    assert phase({"spec.md": SPEC}) == SddPhase.RESEARCH_DONE
    # A clarification marker anywhere holds the family at specified.
    assert phase({"spec.md": SPEC + "\n[NEEDS CLARIFICATION: who?]\n"}) == SddPhase.SPECIFIED
    # An unchecked item under an open-questions heading of research.md holds it there too; elsewhere it is no question.
    open_research = "# Research\n\n## Open questions\n\n- [ ] Which index?\n"
    assert phase({"spec.md": SPEC, "research.md": open_research}) == SddPhase.SPECIFIED
    assert phase({"spec.md": SPEC, "research.md": "# Research\n\n## Notes\n\n- [ ] later\n"}) == SddPhase.RESEARCH_DONE
    docs = {"spec.md": SPEC, "plan.md": "# plan\n"}
    assert phase(docs, check=broken) == SddPhase.RESEARCH_DONE
    assert phase(docs, check=clean) == SddPhase.PLAN_ACCEPTED
    docs["tasks.md"] = "# Tasks\n\n- [ ] T001 FAM-R001 only one\n"
    assert phase(docs) == SddPhase.PLAN_ACCEPTED  # FAM-R002 has no task line
    docs["tasks.md"] = TASKS_OPEN
    assert phase(docs) == SddPhase.TASKS_READY
    docs["tasks.md"] = TASKS_STARTED
    assert phase(docs) == SddPhase.IMPLEMENTING
    docs["tasks.md"] = TASKS_OPEN
    assert phase(docs, rows=_rows("LANDED", "SPECIFIED")) == SddPhase.IMPLEMENTING
    assert phase(docs, rows=_rows("VERIFIED", "VERIFIED")) == SddPhase.VERIFIED
    assert phase(docs, rows=_rows("VERIFIED", "RETIRED")) == SddPhase.VERIFIED  # retired rows do not count
    # A retired or rollup row needs no task line.
    docs["tasks.md"] = "# Tasks\n\n- [ ] T001 FAM-R001 only one\n"
    mixed = [{"id": "FAM-R001", "status": "SPECIFIED"}, {"id": "FAM-R002", "status": "SPECIFIED", "rollup": True}]
    assert phase(docs, rows=mixed) == SddPhase.TASKS_READY


@pytest.mark.spec("PIPE-PAGES-R054.2")
def test_plan_conformance_wrapper_reports_findings_for_text() -> None:
    from pipelines_hooks.specs.plan_conformance import check_plan_text

    template = "# <SPEC-ID> — Implementation plan\n\n## Summary\n\nx\n\n## Build contract\n\ny\n"
    good = "# FAM-X — Implementation plan\n\n## Summary\n\nDone.\n\n## Build contract\n\nDone.\n"
    assert check_plan_text(good, template, {"FAM-X-R001"}) == []
    found = check_plan_text("# FAM-X — Implementation plan\n\n## Summary\n\nDone.\n", template, set())
    assert any("Build contract" in f for f in found)


R030 = f"{PREFIX}-R030"
GO = """
const hit=(id)=>window.__arch.search(id)[0];
const wait=(ms)=>new Promise(r=>setTimeout(r,ms));
"""


def _run(monkeypatch, tmp_path: Path, script: str, fragment: str = "") -> dict:
    site = build_site(monkeypatch, tmp_path)
    with serve(site) as url:
        return drive(tmp_path, url + fragment, GO + script)


@pytest.mark.spec("PIPE-PAGES-R054.3")
@NEEDS_BROWSER
def test_mode_switch_changes_node_style_without_moving_nodes(monkeypatch, tmp_path: Path) -> None:
    out = _run(
        monkeypatch,
        tmp_path,
        """
const node=hit("%s").node, rects=()=>JSON.stringify([window.__arch.rect("root"),window.__arch.rect(node)]);
const base=rects(), styles={}, pressed={};
for (const b of document.querySelectorAll("#modes button")){ b.click(); await wait(80);
  styles[b.dataset.mode]=window.__arch.modeStyle(node); pressed[b.dataset.mode]=document.querySelector('#modes [aria-pressed="true"]').dataset.mode;
  if(rects()!==base) return {moved:b.dataset.mode}; }
const group=document.getElementById("modes");
return {moved:"", styles, pressed, role:group.getAttribute("role"), label:group.getAttribute("aria-label"), count:group.querySelectorAll("button").length};
"""
        % R030,
    )
    assert out["moved"] == "" and out["role"] == "group" and out["count"] == 5 and out["label"] == "Diagram mode"
    assert out["styles"]["architecture"]["fill"] == "" and out["styles"]["delivery"]["fill"].startswith("rgba(")
    assert out["styles"]["sdd"]["badge"] in {
        "specified",
        "research-done",
        "plan-accepted",
        "tasks-ready",
        "implementing",
        "verified",
    }
    assert out["styles"]["priority"]["ring"] >= 1 and set(out["pressed"].values()) == set(out["pressed"])


@pytest.mark.spec("PIPE-PAGES-R054.4")
@NEEDS_BROWSER
def test_empty_nodes_stay_neutral_and_unknown_mode_falls_back(monkeypatch, tmp_path: Path) -> None:
    out = _run(
        monkeypatch,
        tmp_path,
        """
window.__arch.setMode("delivery"); await wait(80);
const empty=window.__arch.modeStyle("root");
location.hash="#mode=bogus"; await wait(500);
return {empty, mode:window.__arch.mode, status:document.getElementById("qstatus").textContent};
""",
    )
    assert out["empty"] == {"fill": "", "ring": 0, "badge": "no own rows"}
    assert out["mode"] == "architecture" and "Unknown view value ignored: mode bogus" in out["status"]
    template = (PKG / "template.html").read_text()
    assert "no own rows" in template and "prefers-reduced-motion" in template


@pytest.mark.spec("PIPE-PAGES-R054.5")
@NEEDS_LAYOUT
def test_dependency_edges_match_the_next_up_prerequisites(monkeypatch, tmp_path: Path) -> None:
    site = build_site(monkeypatch, tmp_path)
    tree = payload(site)["tree"]
    source, target = node_of(site, R030), node_of(site, f"{ADGUARD}-R002")
    assert source != target
    assert [source, target, 1, [[R030, f"{ADGUARD}-R002"]]] in tree["deps"]
    # Each pair is a prerequisite that is itself an open row, so it appears in the Next up or Delivery path views.
    open_ids = {r["id"] for r in [s for n in _nodes(tree) for s in n["specs"]] if r["status"] != "VERIFIED"}
    assert all(pre in open_ids for _, _, _, pairs in tree["deps"] for pre, _ in pairs)
    assert "function drawDeps" in (PKG / "template.html").read_text()


def _nodes(tree: dict):
    yield tree
    for child in tree["children"]:
        yield from _nodes(child)


@pytest.mark.spec("PIPE-PAGES-R054.6")
@NEEDS_BROWSER
def test_sdd_mode_legend_counts_match_the_computed_phases_in_a_browser(monkeypatch, tmp_path: Path) -> None:
    site = build_site(monkeypatch, tmp_path)
    cards = payload(site)["tree"]["cards"]
    expected: dict[str, int] = {}
    for fams in cards.values():
        for card in fams.values():
            label = [
                "no spec",
                "specified",
                "research-done",
                "plan-accepted",
                "tasks-ready",
                "implementing",
                "verified",
            ][card["s"]]
            expected[label] = expected.get(label, 0) + 1
    assert len(expected) >= 3, expected  # the fixture spans several phases
    with serve(site) as url:
        out = drive(
            tmp_path,
            url,
            GO
            + """
document.querySelector('#modes [data-mode="sdd"]').click(); await wait(120);
const counts={}; for (const s of document.querySelectorAll("#modelegend [data-phase]")){ const m=/^(.*) (\\d+)$/.exec(s.textContent); counts[m[1]]=+m[2]; }
return {counts, mode:window.__arch.mode};
""",
        )
    assert out["mode"] == "sdd" and out["counts"] == expected
