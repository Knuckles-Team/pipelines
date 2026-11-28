"""Canopy deep links and the agent export (PIPE-PAGES-R057)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import export  # noqa: E402
import canopy_browser  # noqa: E402
from canopy_browser import ADGUARD, NEEDS_BROWSER, PREFIX, build_site, drive, serve  # noqa: E402

PKG = ROOT / "scripts/architecture_explorer"


def _snap(files: set[str] | None = None, rows: list[dict] | None = None) -> SimpleNamespace:
    base = "specs/fam/"
    files = (
        files if files is not None else {base + n for n in ("requirements.md", "spec.md", "plan.md", "checklists/a.md")}
    )
    rows = (
        rows
        if rows is not None
        else [
            {"id": "FAM-R001", "title": "One", "status": "SPECIFIED", "repo": "pipelines", "family": "fam", "line": 7},
            {"id": "FAM-R002", "title": "Two", "status": "VERIFIED", "repo": "pipelines", "family": "fam", "line": 8},
        ]
    )
    return SimpleNamespace(repo="pipelines", slug="pipelines", head="abc123", files=files, rows=rows)


def _delivery() -> dict:
    return {
        "cards": {"pipelines": {"fam": {"p": "P2"}}},
        "row_node": {"FAM-R001": "core.a", "FAM-R002": "core.b"},
        "scores": {"FAM-R001": {"priority": 12}},
        "release_of": {"FAM-R001": "P2"},
        "row_next": {"FAM-R001": "plan"},
        "row_questions": {"FAM-R001": 2},
    }


@pytest.mark.spec("PIPE-PAGES-R057.1")
def test_export_row_carries_every_present_artifact_path() -> None:
    snap = _snap()
    rows = export.build_rows([snap], snap.rows, _delivery())
    first, second = rows
    assert (first.id, first.part, first.state, first.phase, first.priority, first.release, first.line) == (
        "FAM-R001",
        "core.a",
        "SPECIFIED",
        "P2",
        12,
        "P2",
        7,
    )
    assert first.files == {
        "requirements": "specs/fam/requirements.md",
        "spec": "specs/fam/spec.md",
        "plan": "specs/fam/plan.md",
        "checklists": ["specs/fam/checklists/a.md"],
    }  # tasks, test-spec and research are absent, so they are not listed
    assert (second.release, second.priority, second.next_step) == ("unscheduled", None, "")
    assert (first.next_step, first.open_questions) == ("plan", 2)
    with pytest.raises(Exception):
        first.id = "x"  # frozen
    assert export.ViewSpec(mode="sdd", filters=("plan",)).validate() is None


@pytest.mark.spec("PIPE-PAGES-R057.2")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_hash_round_trips_row_part_mode_filter_release() -> None:
    script = (
        "const A=require('./search.cjs');"
        "const h=A.parseHash('#part=core.a&node=core.b&row=FAM-R001&mode=sdd&filter=plan,ready&release=P1&q=x');"
        "const back=A.parseHash(A.hashFor('core.a','',{row:'FAM-R001',mode:'sdd',filter:['plan','ready'],release:'P1'}));"
        "console.log(JSON.stringify({h,back,old:A.parseHash('#conn.x'),q:A.parseHash('#q=GraphQL%20client')}));"
    )
    out = json.loads(subprocess.run(["node", "-e", script], cwd=PKG, capture_output=True, text=True, check=True).stdout)
    assert out["h"] == {
        "node": "core.a",
        "q": "x",
        "row": "FAM-R001",
        "mode": "sdd",
        "filter": ["plan", "ready"],
        "release": "P1",
    }
    assert out["back"] == {
        "node": "core.a",
        "q": "",
        "row": "FAM-R001",
        "mode": "sdd",
        "filter": ["plan", "ready"],
        "release": "P1",
    }
    assert out["old"]["node"] == "conn.x" and out["q"]["q"] == "GraphQL client"


@pytest.mark.spec("PIPE-PAGES-R057.3")
def test_a_build_writes_rows_json_and_markdown_beside_the_page(tmp_path: Path) -> None:
    snap = _snap()
    paths = export.write_export(tmp_path, [snap], snap.rows, _delivery(), built_at="2026-01-01T00:00:00Z")
    assert [p.relative_to(tmp_path).as_posix() for p in paths] == ["export/rows.json", "export/rows.md"]
    doc = json.loads(paths[0].read_text())
    assert doc["row_count"] == 2 and [r["id"] for r in doc["rows"]] == ["FAM-R001", "FAM-R002"]
    template = (PKG / "template.html").read_text()
    assert "Export JSON" in template and "Export Markdown" in template and "function exportView" in template


@pytest.mark.spec("PIPE-PAGES-R057.4")
def test_unknown_view_values_are_refused_and_unsafe_paths_fail_the_build() -> None:
    for bad in (export.ViewSpec(mode="nope"), export.ViewSpec(filters=("nope",))):
        with pytest.raises(export.ExportRefused):
            bad.validate()
    # Only paths under specs/<family>/ are listed, so craft the unsafe case through a family name holding "..".
    sneaky = _snap(
        {"specs/../requirements.md"},
        [{"id": "X-R001", "title": "", "status": "SPECIFIED", "repo": "pipelines", "family": "..", "line": 1}],
    )
    with pytest.raises(export.ExportRefused) as err:
        export.build_rows([sneaky], sneaky.rows, {})
    assert err.value.code == "unsafe-path"
    lost = _snap()
    with pytest.raises(export.ExportRefused) as err:
        export.build_rows([lost], lost.rows[:1], _delivery())
    assert err.value.code == "export-row-missing" and "FAM-R002" in err.value.detail
    template = (PKG / "template.html").read_text()
    assert "function checkViewHash" in template and "Unknown view value ignored" in template


@pytest.mark.spec("PIPE-PAGES-R057.5")
def test_export_header_digest_is_stable_and_markdown_lists_paths(tmp_path: Path) -> None:
    snap = _snap()
    a, b = tmp_path / "a", tmp_path / "b"
    export.write_export(a, [snap], snap.rows, _delivery(), built_at="2026-01-01T00:00:00Z")
    export.write_export(b, [snap], snap.rows, _delivery(), built_at="2027-02-02T00:00:00Z")
    first, second = json.loads((a / "export/rows.json").read_text()), json.loads((b / "export/rows.json").read_text())
    assert first["schema_version"] == 1 and first["heads"] == {"pipelines": "abc123"} and len(first["digest"]) == 64
    assert first["digest"] == second["digest"] and first["built_at"] != second["built_at"]
    strip = lambda d: {k: v for k, v in d.items() if k != "built_at"}  # noqa: E731
    assert strip(first) == strip(second)
    md = (a / "export/rows.md").read_text()
    assert (
        "- [FAM-R001](https://github.com/Knuckles-Team/pipelines/blob/HEAD/specs/fam/requirements.md) SPECIFIED - "
        in md
    )
    assert "specs/fam/plan.md, specs/fam/checklists/a.md" in md


R030 = f"{PREFIX}-R030"


@pytest.mark.spec("PIPE-PAGES-R057.6")
@pytest.mark.browser
@NEEDS_BROWSER
def test_a_hash_restores_the_view_and_the_export_paths_exist(monkeypatch, tmp_path: Path) -> None:
    site = build_site(monkeypatch, tmp_path)
    target = f"{ADGUARD}-R002"
    with serve(site) as url:
        out = drive(
            tmp_path,
            url + f"#mode=sdd&filter=plan&row={target}",
            """await new Promise(r=>setTimeout(r,800));
return {mode:window.__arch.mode, drawer:window.__arch.drawerRow, pressed:Array.from(document.querySelectorAll('[aria-label="Next step"] [aria-pressed="true"]')).map(b=>b.dataset.next), hash:location.hash};
""",
        )
    assert out["mode"] == "sdd" and out["drawer"] == target and out["pressed"] == ["plan"]
    assert "mode=sdd" in out["hash"] and "row=" in out["hash"]
    doc = json.loads((site / "export/rows.json").read_text())
    tracked = {
        f"specs/{fam}/{name}" for docs in canopy_browser.DOCS.values() for fam, files in docs.items() for name in files
    } | {f"specs/{r['family']}/requirements.md" for rows in canopy_browser.ROWS.values() for r in rows}
    paths = {
        p for r in doc["rows"] for group in r["files"].values() for p in ([group] if isinstance(group, str) else group)
    }
    assert paths and paths <= tracked, paths - tracked


@pytest.mark.spec("PIPE-PAGES-R057.7")
@pytest.mark.browser
@NEEDS_BROWSER
def test_page_without_scripts_lists_parts_and_links_exports(monkeypatch, tmp_path: Path) -> None:
    site = build_site(monkeypatch, tmp_path)
    page = (site / "index.html").read_text()
    block = page[page.index('<noscript><section id="noscript-parts"') : page.index("</noscript>") + 11]
    assert 'href="export/rows.json"' in block and 'href="export/rows.md"' in block
    assert "/blob/HEAD/specs/scion-connector-control/spec.md" in block and "<script" not in block
    with serve(site) as url:
        dom = drive(tmp_path, url, "", scripting=False)
    assert "Parts and spec rows" in dom and "scion-connector-control" in dom
