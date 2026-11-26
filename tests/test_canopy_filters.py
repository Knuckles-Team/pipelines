"""Canopy Next-step chips (PIPE-PAGES-R055)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer.sdd import SddPhase, next_step  # noqa: E402
from canopy_browser import ADGUARD, NEEDS_BROWSER, PREFIX, build_site, drive, manifest, node_of, serve  # noqa: E402

CASES = [
    # (state, phase, in Next up, chip)
    ("SPECIFIED", SddPhase.SPECIFIED, False, "research"),
    ("SPECIFIED", SddPhase.RESEARCH_DONE, False, "plan"),
    ("SPECIFIED", SddPhase.PLAN_ACCEPTED, False, ""),
    ("SPECIFIED", SddPhase.TASKS_READY, True, "ready"),
    ("SPECIFIED", SddPhase.IMPLEMENTING, True, "ready"),
    ("SPECIFIED", SddPhase.TASKS_READY, False, ""),
    ("LANDED", SddPhase.IMPLEMENTING, False, "verify"),
    ("VERIFIED", SddPhase.VERIFIED, False, ""),
    ("RETIRED", 0, False, ""),
]


@pytest.mark.spec("PIPE-PAGES-R055.1")
def test_next_step_maps_phase_and_state_to_one_chip() -> None:
    for state, phase, frontier, chip in CASES:
        assert next_step({"status": state}, int(phase), frontier) == chip, (state, phase, frontier)


@pytest.mark.spec("PIPE-PAGES-R055.2")
def test_chip_rules_follow_the_documented_order() -> None:
    # verify beats ready: a LANDED row in Next up at an implementing family is verified next.
    assert next_step({"status": "LANDED"}, int(SddPhase.IMPLEMENTING), True) == "verify"
    # ready beats plan and research: it only applies at tasks-ready or implementing, so the lower phases fall through.
    assert next_step({"status": "SPECIFIED"}, int(SddPhase.RESEARCH_DONE), True) == "plan"
    assert next_step({"status": "SPECIFIED"}, int(SddPhase.SPECIFIED), True) == "research"
    # Every (state, phase, frontier) combination yields at most one chip value.
    chips = {
        next_step({"status": s}, int(p), f)
        for s in ("SPECIFIED", "LANDED", "VERIFIED")
        for p in SddPhase
        for f in (True, False)
    }
    assert chips <= {"verify", "ready", "plan", "research", ""}


R030 = f"{PREFIX}-R030"
WAIT = "const wait=(ms)=>new Promise(r=>setTimeout(r,ms));\n"
CHIPS = """const chips=()=>Object.fromEntries(Array.from(document.querySelectorAll('[aria-label="Next step"] button')).map(b=>[b.dataset.next,{count:+/(\\d+)$/.exec(b.textContent)[1],disabled:b.disabled,pressed:b.getAttribute("aria-pressed"),title:b.title}]));
const listed=()=>Array.from(document.querySelectorAll("#specsec li[data-spec]")).map(li=>li.dataset.spec);
"""


def _run(monkeypatch, tmp_path: Path, script: str, fragment: str = "", **kw) -> tuple[dict, Path]:
    site = build_site(monkeypatch, tmp_path, **kw)
    with serve(site) as url:
        return drive(tmp_path, url + fragment, WAIT + CHIPS + script), site


def _export_rows(site: Path) -> list[dict]:
    return json.loads((site / "export/rows.json").read_text())["rows"]


@pytest.mark.spec("PIPE-PAGES-R055.3")
@NEEDS_BROWSER
def test_chips_combine_with_status_and_release_filters(monkeypatch, tmp_path: Path) -> None:
    out, _ = _run(
        monkeypatch,
        tmp_path,
        """
const before=chips();
document.querySelector('[data-next="ready"]').click(); await wait(200);
const ready={listed:listed(), hash:location.hash, group:document.querySelector('[aria-label="Next step"]').getAttribute("role")};
const status=Array.from(document.querySelectorAll('[aria-label="Status filter"] button')).find(b=>/^LANDED/.test(b.textContent));
if(status){ status.click(); await wait(200); }
return {before, ready, combined:listed(), hasLanded:!!status};
""",
        manifests=[manifest("P1", "P1", [f"{PREFIX}-R030"])],
    )
    assert out["ready"]["listed"] == [R030] and out["ready"]["hash"].endswith("filter=ready")
    assert out["ready"]["group"] == "group" and out["before"]["ready"]["count"] == 1
    assert out["combined"] == [] or not out["hasLanded"]  # AND logic: the one ready row is not LANDED


@pytest.mark.spec("PIPE-PAGES-R055.4")
@NEEDS_BROWSER
def test_empty_chips_are_disabled_and_unknown_names_are_ignored(monkeypatch, tmp_path: Path) -> None:
    site = build_site(monkeypatch, tmp_path)
    node = node_of(site, f"{ADGUARD}-R002")
    with serve(site) as url:
        out = drive(
            tmp_path,
            url,
            WAIT
            + CHIPS
            + """
window.__arch.go(%r,{hit:true,open:true,instant:true}); await wait(700);
const state=chips();
location.hash="#filter=bogus"; await wait(400);
return {state, status:document.getElementById("qstatus").textContent, after:chips(), label:document.querySelector('[aria-label="Next step"]').getAttribute("aria-label")};
"""
            % node,
        )
    assert out["state"]["ready"] == {
        "count": 0,
        "disabled": True,
        "pressed": "false",
        "title": out["state"]["ready"]["title"],
    }
    assert out["state"]["plan"]["count"] == 1 and out["state"]["plan"]["disabled"] is False
    assert "Unknown view value ignored: filter bogus" in out["status"] and out["after"]["plan"]["pressed"] == "false"


@pytest.mark.spec("PIPE-PAGES-R055.5")
@NEEDS_BROWSER
def test_chip_counts_and_export_next_step_agree(monkeypatch, tmp_path: Path) -> None:
    out, site = _run(
        monkeypatch, tmp_path, "return {chips:chips(), legend:document.querySelector('.nextlegend').textContent};"
    )
    exported: dict[str, int] = {}
    for row in _export_rows(site):
        if row["next_step"]:
            exported[row["next_step"]] = exported.get(row["next_step"], 0) + 1
    assert {k: v["count"] for k, v in out["chips"].items() if v["count"]} == exported
    assert all(v["title"] for v in out["chips"].values()) and "Ready to implement" in out["legend"]


@pytest.mark.spec("PIPE-PAGES-R055.6")
@NEEDS_BROWSER
def test_the_ready_filter_lists_only_next_up_rows_in_a_browser(monkeypatch, tmp_path: Path) -> None:
    out, site = _run(monkeypatch, tmp_path, "return {listed:listed(), chips:chips()};", fragment="#filter=ready")
    assert out["listed"] == [r["id"] for r in _export_rows(site) if r["next_step"] == "ready"] == [R030]
    assert out["chips"]["ready"]["pressed"] == "true"
