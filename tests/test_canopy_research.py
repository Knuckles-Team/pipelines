"""Canopy open research questions (PIPE-PAGES-R058)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import build as explorer  # noqa: E402
from scripts.architecture_explorer import sdd  # noqa: E402
from canopy_browser import NEEDS_BROWSER, PKG, build_site, drive, node_of, serve  # noqa: E402

RESEARCH = (
    "# Research\n\n## Decisions\n\n- [ ] not a question FAM-R009\n\n## Open questions\n\n"
    "- [ ] Which index serves FAM-R001?\n- [x] Settled one\n- [ ] A family-wide question\n\n"
    "## Unresolved\n\n- [ ] Is FAM-R002 retired?\n"
)
SPEC = "# FAM - Fam\n\nThe cutoff is [NEEDS CLARIFICATION: how long?] for FAM-R002.\n"


@pytest.mark.spec("PIPE-PAGES-R058.1")
def test_open_questions_find_markers_and_unchecked_research_items() -> None:
    found = sdd.open_questions({"spec.md": SPEC, "research.md": RESEARCH})
    by_kind = {(q["kind"], q["doc"], q["line"], q["row"]) for q in found}
    assert ("marker", "spec.md", 3, "FAM-R002") in by_kind
    assert ("open", "research.md", 9, "FAM-R001") in by_kind
    assert ("open", "research.md", 11, "") in by_kind
    assert ("open", "research.md", 15, "FAM-R002") in by_kind
    assert len(found) == 4  # the checked item and the item under Decisions are no questions
    assert set(found[0]) == {"kind", "text", "doc", "line", "row"}


@pytest.mark.spec("PIPE-PAGES-R058.2")
def test_counts_follow_the_own_rows_rule_and_zero_shows_no_badge() -> None:
    rows = [{"id": "FAM-R001", "status": "SPECIFIED"}, {"id": "FAM-R002", "status": "SPECIFIED"}]
    card = sdd.family_card({"spec.md": SPEC, "research.md": RESEARCH}, set(), "fam", [], rows)
    assert card["q"] == 4
    quiet = sdd.family_card({"spec.md": "# FAM - Fam\n"}, set(), "fam", [], rows)
    assert "q" not in quiet and "u" not in quiet
    snap = type(
        "S",
        (),
        {
            "repo": "r",
            "rows": [dict(r, family="fam") for r in rows],
            "files": set(),
            "docs": {"fam": {"spec.md": SPEC, "research.md": RESEARCH}},
        },
    )
    cards = {"r": {"fam": card}}
    _, counts = explorer.row_facts([snap], cards, set())
    assert counts == {"FAM-R001": 1, "FAM-R002": 2}
    entry = explorer.spec_entry(
        dict(rows[1], repo="r", family="fam", title="t"),
        {"scores": {}, "frontier_set": set(), "unserved_set": set(), "row_questions": counts},
    )
    assert entry["q"] == 2
    zero = explorer.spec_entry(
        dict(rows[0], repo="r", family="fam", title="t"),
        {"scores": {}, "frontier_set": set(), "unserved_set": set(), "row_questions": {}},
    )
    assert "q" not in zero


@pytest.mark.spec("PIPE-PAGES-R058.4")
def test_unreadable_research_marks_the_family_without_failing_the_build() -> None:
    files = {"specs/fam/research.md", "specs/fam/spec.md"}
    found = sdd.open_questions({"spec.md": "# FAM\n"}, files, "fam")
    assert [q["kind"] for q in found] == ["unreadable"]
    card = sdd.family_card({"spec.md": "# FAM\n"}, files, "fam", [], [{"id": "FAM-R001", "status": "SPECIFIED"}])
    assert card["u"] == "research unreadable" and "q" not in card
    # An unchecked item outside an open-questions heading is not a question.
    assert sdd.open_questions({"research.md": "# R\n\n## Notes\n\n- [ ] later\n"}) == []


ROW = "CONN-ANSIBLE-TOWER-MCP-R002"
WAIT = "const wait=(ms)=>new Promise(r=>setTimeout(r,ms));\n"


@pytest.mark.spec("PIPE-PAGES-R058.3")
@pytest.mark.browser
@NEEDS_BROWSER
def test_badges_render_on_node_card_and_row_with_screen_reader_text(monkeypatch, tmp_path: Path) -> None:
    site = build_site(monkeypatch, tmp_path)
    node = node_of(site, ROW)
    with serve(site) as url:
        out = drive(
            tmp_path,
            url,
            WAIT
            + """
window.__arch.go(%r,{hit:true,open:true,instant:true}); await wait(700);
const row=document.querySelector('[data-spec="%s"] .oq');
return {node:window.__arch.ownQuestions(%r), row:row&&{label:row.getAttribute("aria-label"), text:row.textContent, href:row.getAttribute("href")},
  card:Array.from(document.querySelectorAll(".dcard .oq")).map(c=>c.textContent)};
"""
            % (node, ROW, node),
        )
    assert out["node"] == 2
    assert out["row"] == {"label": "2 open questions", "text": "2 open questions", "href": f"#row={ROW}"}
    assert out["card"] == [] or all("open questions" in c for c in out["card"])
    template = (PKG / "template.html").read_text()
    assert "ownQuestions(n)" in template and "open questions" in template


@pytest.mark.spec("PIPE-PAGES-R058.5")
@pytest.mark.browser
@NEEDS_BROWSER
def test_drawer_and_export_list_the_questions_with_document_and_line(monkeypatch, tmp_path: Path) -> None:
    site = build_site(monkeypatch, tmp_path)
    export = {r["id"]: r for r in json.loads((site / "export/rows.json").read_text())["rows"]}
    assert export[ROW]["open_questions"] == 2
    with serve(site) as url:
        out = drive(
            tmp_path,
            url + f"#row={ROW}",
            WAIT
            + """
await wait(900);
const items=Array.from(document.querySelectorAll("#drawer .questions li")).map(li=>({text:li.textContent, href:li.querySelector("a")&&li.querySelector("a").href}));
return {items};
""",
        )
    assert [i["text"].split(" ")[0] for i in out["items"]] == ["research.md:5", "research.md:6"]
    assert all(
        i["href"].startswith("https://github.com/Knuckles-Team/ansible-tower-mcp/blob/HEAD/specs/")
        for i in out["items"]
    )


@pytest.mark.spec("PIPE-PAGES-R058.6")
@pytest.mark.browser
@NEEDS_BROWSER
def test_research_badge_and_drawer_list_in_a_browser(monkeypatch, tmp_path: Path) -> None:
    site = build_site(monkeypatch, tmp_path)
    node = node_of(site, ROW)
    with serve(site) as url:
        out = drive(
            tmp_path,
            url + f"#row={ROW}",
            WAIT
            + """
await wait(900);
return {badge:window.__arch.ownQuestions(%r), listed:document.querySelectorAll("#drawer .questions li").length,
  heading:Array.from(document.querySelectorAll("#drawer h4")).map(h=>h.textContent).find(t=>/research questions/.test(t))};
"""
            % node,
        )
    assert out["badge"] == 2 and out["listed"] == 2 and out["heading"] == "Open research questions (2)"
