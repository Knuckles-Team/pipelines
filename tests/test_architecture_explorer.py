"""Architecture explorer: placement, crossings, layout wiring and page output."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import build as explorer  # noqa: E402
from scripts.architecture_explorer import sources  # noqa: E402
from scripts.architecture_explorer.geometry import count_crossings, crossings_in  # noqa: E402
from scripts.architecture_explorer.place import Placer, Tree, unmapped_violations, validate_code  # noqa: E402
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


def _model_with_external() -> dict:
    model = _model()
    model["children"].insert(
        0,
        {
            "id": "people",
            "label": "People",
            "desc": "People.",
            "repo": "core",
            "external": True,
            "fam": ["fam"],
            "kw": "solver",
        },
    )
    model["children"][1]["children"].append({"id": "core.misc", "label": "Misc", "desc": "Misc.", "kw": "sibling part"})
    model["children"].append(
        {
            "id": "side",
            "label": "Side",
            "desc": "Side.",
            "repo": "core",
            "fam": ["side"],
            "children": [{"id": "side.a", "label": "A", "desc": "A.", "kw": "alpha"}],
        }
    )
    return model


@pytest.mark.spec("PIPE-PAGES-R042")
def test_external_parts_never_take_rows() -> None:
    tree = Tree(_model_with_external())
    rows = [_row("CORE-R001", "Exact solver certificate"), _row("CORE-R010", "No rule matches this")]
    direct = Placer(tree).run(rows)
    assert not direct.get("people")
    where = {r["id"]: nid for nid, rs in direct.items() for r in rs}
    assert where["CORE-R001"] == "core.solver"
    assert unmapped_violations(tree, {"people": rows[:1]}, ["core:CORE-R001"]) == ["core:CORE-R001"]


@pytest.mark.spec("PIPE-PAGES-R042")
def test_shipped_external_parts_take_no_rows_and_declare_no_rules() -> None:
    model = json.loads((PKG / "model.json").read_text())
    tree = Tree(model)
    external = [n for n in tree.nodes.values() if n.get("external")]
    assert {n["id"] for n in external} >= {"people", "clients"}
    for node in external:
        assert not node["children"] and not node.get("fam") and not node.get("kw") and not node.get("ids")


@pytest.mark.spec("PIPE-PAGES-R042")
def test_sibling_family_title_and_parent_place_rows_before_unmapped() -> None:
    tree = Tree(_model_with_external())
    rows = [
        _row("SIDE-R001", "Belongs to a sibling part", family="side"),
        _row("SIDE-R001.1", "Model", family="side"),
        _row("SIDE-R002", "Nothing names it", family="side"),
    ]
    direct = Placer(tree).run(rows)
    where = {r["id"]: nid for nid, rs in direct.items() for r in rs}
    assert where["SIDE-R001"] == "core.misc"
    assert where["SIDE-R001.1"] == "core.misc"
    assert where["SIDE-R002"] == "side.unmapped"
    assert unmapped_violations(tree, direct, []) == ["core:SIDE-R002"]
    assert unmapped_violations(tree, direct, ["core:SIDE-R002"]) == []


@pytest.mark.spec("PIPE-PAGES-R042")
def test_a_row_on_a_container_descends_to_a_leaf_or_fails_the_gate() -> None:
    model = _model()
    model["children"][0]["children"][0]["children"] = [
        {"id": "core.solver.exact", "label": "Exact", "desc": "Exact.", "kw": "certificate"}
    ]
    tree = Tree(model)
    rows = [
        _row("CORE-R003", "Unrelated title", text="Touches `crates/solve/a.rs` and a certificate."),
        _row("CORE-R004", "Unrelated title", text="Touches `crates/solve/b.rs`."),
    ]
    direct = Placer(tree).run(rows)
    where = {r["id"]: nid for nid, rs in direct.items() for r in rs}
    assert where["CORE-R003"] == "core.solver.exact"
    assert where["CORE-R004"] == "core.solver"
    assert unmapped_violations(tree, direct, []) == ["core:CORE-R004"]


@pytest.mark.spec("PIPE-PAGES-R042")
def test_no_leftover_bucket_labels_in_the_shipped_model() -> None:
    tree = Tree(json.loads((PKG / "model.json").read_text()))
    assert not [n["id"] for n in tree.nodes.values() if n["label"].strip().lower() in {"other", "misc", "unmapped"}]


@pytest.mark.spec("PIPE-PAGES-R042")
def test_shipped_unmapped_allowlist_is_reviewed_and_empty() -> None:
    """Every unmapped row fails the build unless the model's reviewed allowlist names it; keep it empty."""
    model = json.loads((PKG / "model.json").read_text())
    assert model["unmapped_allow"] == []


@pytest.mark.spec("PIPE-PAGES-R042")
def test_build_fails_on_an_unmapped_row(monkeypatch) -> None:
    rows = [_row("EG-SCM-R999", "Nothing names this row", family="source-changesets", repo="epistemic-graph")]

    def fake_load(registry, mode, workspace=None, workers=12):
        return [
            Snapshot(repo=e["name"], slug=e["slug"], head="abc", rows=rows if e["name"] == "epistemic-graph" else [])
            for e in registry
        ]

    monkeypatch.setattr(explorer, "load_all", fake_load)
    monkeypatch.setattr(explorer, "run_layout", lambda levels: {})
    _, meta = explorer.build("github", None)
    assert meta["unmapped_violations"] == ["epistemic-graph:EG-SCM-R999"]


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

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
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


def _fake_loader(rows_by_repo: dict[str, list[dict]]):
    def fake_load(registry, mode, workspace=None, workers=12):
        return [
            Snapshot(repo=e["name"], slug=e["slug"], head="h-" + e["name"][:4], rows=rows_by_repo.get(e["name"], []))
            for e in registry
        ]

    return fake_load


def _ids(node: dict) -> set[str]:
    out = {s["id"] for s in node["specs"]}
    for child in node["children"]:
        out |= _ids(child)
    return out


@pytest.mark.spec("PIPE-PAGES-R042")
@pytest.mark.skipif(
    shutil.which("node") is None or not (PKG / "node_modules/elkjs").exists(), reason="layout engine not installed"
)
def test_a_deleted_row_disappears_from_the_generated_tree(monkeypatch) -> None:
    keep = _row("EG-SCM-R001", "Content-addressed blob store", family="source-changesets", repo="epistemic-graph")
    gone = _row("EG-SCM-R002", "Changeset replay", family="source-changesets", repo="epistemic-graph")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(explorer, "load_all", _fake_loader({"epistemic-graph": [keep, gone]}))
    before, meta = explorer.build("github", None)
    assert {"EG-SCM-R001", "EG-SCM-R002"} <= _ids(before)
    monkeypatch.setattr(explorer, "load_all", _fake_loader({"epistemic-graph": [keep]}))
    after, meta = explorer.build("github", None)
    assert "EG-SCM-R001" in _ids(after) and "EG-SCM-R002" not in _ids(after)
    assert meta["rows"] == 1 and meta["heads"]["epistemic-graph"] == "h-epis"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", meta["built_at"])


@pytest.mark.spec("PIPE-PAGES-R042")
def test_discovery_drops_removed_repositories_and_adds_new_ones() -> None:
    registry = [
        {"name": "arbora", "slug": "arbora", "local": "x", "kind": "core"},
        {"name": "old-mcp", "slug": "old-mcp", "local": "y", "kind": "connector"},
    ]
    found = {"arbora": "a" * 40, "new-mcp": "b" * 40, ".github": "c" * 40}
    scanned = sources.reconcile(registry, found)
    assert [e["name"] for e in scanned] == ["arbora", "new-mcp"]
    assert scanned[0]["sha"] == "a" * 40 and scanned[1]["discovered"] is True
    assert sources.scan_set(registry, "local", "token") == registry
    assert sources.scan_set(registry, "github", None) == registry


@pytest.mark.spec("PIPE-PAGES-R042")
def test_the_fleet_matches_the_scan_set() -> None:
    model = json.loads((PKG / "model.json").read_text())
    registry = json.loads((PKG / "registry.json").read_text())["repositories"]
    scanned = [e for e in registry if e["name"] != "adguard-home-agent"]
    scanned.append({"name": "brand-new-mcp", "slug": "brand-new-mcp", "kind": "connector", "discovered": True})
    explorer.fit_fleet(model, scanned)
    tree = Tree(model)
    repos = {n["repo"] for n in tree.nodes.values() if n["id"].startswith("conn.") and not n["children"]}
    assert "adguard-home-agent" not in repos
    assert tree.nodes["conn.discovered.brand-new-mcp"]["fam"] == ["*"]
    assert tree.nodes["connectors"]["role"].startswith(f"{len(repos)} connectors")


@pytest.mark.spec("PIPE-PAGES-R042")
def test_page_carries_a_freshness_stamp() -> None:
    html = (PKG / "template.html").read_text()
    assert 'id="fresh"' in html and "META.built_at" in html and "/commit/" in html


@pytest.mark.spec("PIPE-PAGES-R042")
def test_repository_copies_redirect_to_the_canonical_explorer(tmp_path: Path) -> None:
    page = tmp_path / "architecture/index.html"
    assert explorer.main(["--redirect", "--page", str(page)]) == 0
    html = page.read_text()
    assert html.startswith("<!doctype html>")
    assert 'location.replace("https://knuckles-team.github.io/.github/architecture/" + location.hash)' in html
    assert '<link rel="canonical" href="https://knuckles-team.github.io/.github/architecture/">' in html
