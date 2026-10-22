"""Architecture explorer: placement, crossings, layout wiring and page output."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import build as explorer  # noqa: E402
from scripts.architecture_explorer.geometry import count_crossings, crossings_in  # noqa: E402
from scripts.architecture_explorer.place import Placer, Tree, validate_code  # noqa: E402
from scripts.architecture_explorer.sources import Snapshot, requirement_text, spec_dirs  # noqa: E402

PKG = ROOT / "scripts/architecture_explorer"


def _row(rid: str, title: str, family: str = "fam", repo: str = "core", text: str = "") -> dict:
    return {"id": rid, "title": title, "status": "SPECIFIED", "repo": repo, "family": family, "text": text, "req": text}


def _model() -> dict:
    return {
        "id": "root",
        "label": "Root",
        "desc": "Root.",
        "children": [
            {
                "id": "core",
                "label": "Core",
                "desc": "Core.",
                "repo": "core",
                "fam": ["fam"],
                "children": [
                    {
                        "id": "core.solver",
                        "label": "Solver",
                        "desc": "Solver.",
                        "kw": "solver",
                        "code": ["crates/solve"],
                    },
                    {"id": "core.ledger", "label": "Ledger", "desc": "Ledger.", "ids": ["CORE-R009"]},
                ],
            },
        ],
    }


@pytest.mark.spec("PIPE-PAGES-R042")
def test_rows_land_on_the_deepest_matching_part() -> None:
    tree = Tree(_model())
    rows = [
        _row("CORE-R001", "Exact solver certificate"),
        _row("CORE-R002", "Unrelated title", text="Touches `crates/solve/search.rs`."),
        _row("CORE-R002.1", "Model"),
        _row("CORE-R009", "Anything"),
        _row("CORE-R010", "No rule matches this"),
        _row("OTHER-R001", "Family nobody owns", family="other"),
    ]
    direct = Placer(tree).run(rows)
    where = {r["id"]: nid for nid, rs in direct.items() for r in rs}
    assert where["CORE-R001"] == "core.solver"
    assert where["CORE-R002"] == "core.solver"
    assert where["CORE-R002.1"] == "core.solver"
    assert where["CORE-R009"] == "core.ledger"
    assert where["CORE-R010"] == "core.unmapped"
    assert where["OTHER-R001"] == "root.unmapped"
    assert sum(len(v) for v in direct.values()) == len(rows)


@pytest.mark.spec("PIPE-PAGES-R042")
def test_absent_code_paths_are_dropped_not_trusted() -> None:
    tree = Tree(_model())
    dropped = validate_code(tree, {"core": {"crates/other/lib.rs"}})
    assert dropped == [("core.solver", "crates/solve")]
    assert tree.nodes["core.solver"]["code"] == []


@pytest.mark.spec("PIPE-PAGES-R042")
def test_crossings_count_only_interior_crossings_of_unrelated_edges() -> None:
    cross = [{"from": "a", "to": "b", "pts": [[0, 5], [10, 5]]}, {"from": "c", "to": "d", "pts": [[5, 0], [5, 10]]}]
    shared = [{"from": "a", "to": "b", "pts": [[0, 5], [10, 5]]}, {"from": "a", "to": "d", "pts": [[5, 0], [5, 10]]}]
    touch = [{"from": "a", "to": "b", "pts": [[0, 5], [10, 5]]}, {"from": "c", "to": "d", "pts": [[10, 0], [10, 10]]}]
    assert crossings_in(cross) == 1
    assert crossings_in(shared) == 0
    assert crossings_in(touch) == 0
    assert count_crossings({"x": {"edges": cross}, "y": {"edges": touch}}) == {"total": 1, "levels": {"x": 1}}


def test_spec_sources_parse_tables_and_skip_templates() -> None:
    files = {"specs/a/status.json", "specs/_template/status.json", "specs/a/requirements.md", "specs/README.md"}
    assert spec_dirs(files) == ["a"]
    text = requirement_text("| ID | R |\n|---|---|\n| `X-R001` | **Title.** Body | Test |\n")
    assert list(text) == ["X-R001"]


@pytest.mark.spec("PIPE-PAGES-R042")
def test_shipped_model_covers_every_registered_connector() -> None:
    model = json.loads((PKG / "model.json").read_text())
    registry = json.loads((PKG / "registry.json").read_text())
    tree = Tree(model)
    connectors = {e["name"] for e in registry["repositories"] if e["kind"] == "connector"}
    placed = {n["repo"] for n in tree.nodes.values() if n["id"].startswith("conn.") and not n["children"]}
    assert connectors == placed
    assert set(registry["pages_node"].values()) <= set(tree.nodes)


@pytest.mark.spec("PIPE-PAGES-R042")
@pytest.mark.skipif(
    shutil.which("node") is None or not (PKG / "node_modules/elkjs").exists(), reason="layout engine not installed"
)
def test_page_builds_offline_with_both_variants(monkeypatch, tmp_path: Path) -> None:
    rows = [_row("EG-SCM-R001", "Content-addressed blob store", family="source-changesets", repo="epistemic-graph")]

    def fake_load(registry, mode, workspace=None, workers=12):
        return [
            Snapshot(repo=e["name"], slug=e["slug"], head="abc", rows=rows if e["name"] == "epistemic-graph" else [])
            for e in registry
        ]

    monkeypatch.setattr(explorer, "load_all", fake_load)
    page, body = tmp_path / "index.html", tmp_path / "artifact.html"
    assert explorer.main(["--mode", "github", "--page", str(page), "--artifact", str(body)]) == 0
    full, bare = page.read_text(), body.read_text()
    assert full.startswith("<!doctype html>") and full.rstrip().endswith("</html>")
    assert not bare.lstrip().lower().startswith("<!doctype") and "<body" not in bare
    assert "<title>Arbora Architecture Explorer</title>" in bare[:8192]
    assert '"EG-SCM-R001"' in bare and "/*__DATA__*/" not in bare


def test_theme_link_bypasses_instant_navigation() -> None:
    """The explorer is a standalone page; instant navigation would swap in its body without its styles."""
    from pathlib import Path

    html = Path(__file__).resolve().parents[1].joinpath("templates/mkdocs-theme/overrides/main.html").read_text()
    link = next(line for line in html.splitlines() if "site-architecture__link" in line)
    assert 'target="_self"' in link
