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
from scripts.architecture_explorer import details, sources  # noqa: E402
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
    assert {n["id"] for n in external} >= {"people", "clients", "sources"}
    for node in external:
        assert not node["children"] and not node.get("fam") and not node.get("kw") and not node.get("ids")


@pytest.mark.spec("PIPE-PAGES-R042.4")
def test_every_person_layer_top_node_is_external_and_no_row_places_on_it() -> None:
    model = json.loads((PKG / "model.json").read_text())
    tree = Tree(model)
    people_layer = [n for n in model["children"] if n.get("layer") == "person"]
    assert {n["id"] for n in people_layer} == {"people", "clients", "sources"}
    assert all(n.get("external") for n in people_layer)
    rows = [
        _row("CORE-R001", "Exact solver certificate"),
        _row("CORE-R002", "Source system record read"),
        _row("CORE-R003", "No rule matches this"),
    ]
    direct = Placer(tree).run(rows)
    external = {n["id"] for n in tree.nodes.values() if n.get("external")}
    assert external >= {"people", "clients", "sources"}
    assert not [nid for nid in direct if nid in external and direct[nid]]


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
    rows = [_row("EG-SCM-R999", "Nothing names this row", family="source-changesets", repo="medulla")]

    def fake_load(registry, mode, workspace=None, workers=12):
        return [
            Snapshot(repo=e["name"], slug=e["slug"], head="abc", rows=rows if e["name"] == "medulla" else [])
            for e in registry
        ]

    monkeypatch.setattr(explorer, "load_all", fake_load)
    monkeypatch.setattr(explorer, "run_layout", lambda levels: {})
    _, meta = explorer.build("github", None)
    assert meta["unmapped_violations"] == ["medulla:EG-SCM-R999"]


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
    rows = [_row("EG-SCM-R001", "Content-addressed blob store", family="source-changesets", repo="medulla")]

    def fake_load(registry, mode, workspace=None, workers=12):
        return [
            Snapshot(repo=e["name"], slug=e["slug"], head="abc", rows=rows if e["name"] == "medulla" else [])
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
    keep = _row("EG-SCM-R001", "Content-addressed blob store", family="source-changesets", repo="medulla")
    gone = _row("EG-SCM-R002", "Changeset replay", family="source-changesets", repo="medulla")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(explorer, "load_all", _fake_loader({"medulla": [keep, gone]}))
    before, meta = explorer.build("github", None)
    assert {"EG-SCM-R001", "EG-SCM-R002"} <= _ids(before)
    monkeypatch.setattr(explorer, "load_all", _fake_loader({"medulla": [keep]}))
    after, meta = explorer.build("github", None)
    assert "EG-SCM-R001" in _ids(after) and "EG-SCM-R002" not in _ids(after)
    assert meta["rows"] == 1 and meta["heads"]["medulla"] == "h-medu"
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


@pytest.mark.spec("PIPE-PAGES-R042.9", "PIPE-PAGES-R042.7")
def test_renamed_repositories_keep_ownership_placement_and_canonical_details(tmp_path: Path) -> None:
    registry = json.loads((PKG / "registry.json").read_text())
    expected = {
        "medulla": ("eg", "epistemic-graph", "core"),
        "meristem": ("au", "agent-utilities", "core"),
        "scion-sdk": ("sdk", "agent-connector-sdk", "core"),
        "overstory": ("webui", "agent-webui", "core"),
        "tuig": ("tui", "agent-terminal-ui", "core"),
        "axil": ("geniusbot", "geniusbot", "client"),
    }
    found = {e["slug"]: "a" * 40 for e in registry["repositories"]}
    found["new-mcp"] = "b" * 40
    scanned = sources.reconcile(registry["repositories"], found)
    entries = {e["name"]: e for e in scanned}
    model = json.loads((PKG / "model.json").read_text())
    explorer.fit_fleet(model, scanned)
    tree = Tree(model)
    rows, snaps = [], []
    for slug, (node_id, old_slug, kind) in expected.items():
        entry = entries[slug]
        assert entry["slug"] == slug and entry["kind"] == kind
        assert not entry.get("discovered") and old_slug not in entries
        assert entry["local"] == f"agent-packages/{old_slug}"
        assert registry["pages_node"][slug] == node_id
        assert tree.nodes[node_id]["repo"] == slug
        if slug == "axil":
            family, source = "desktop-client", "geniusbot/backend.py"
            row = _row("GENIUSBOT-CLIENT-R001", "Backend integration", family, slug)
        elif slug == "meristem":
            family, source = "harness-cycle", "agent_utilities/harness/plan.py"
            row = _row("AU-HARNESS-CYCLE-R001.2", "Propose", family, slug)
        else:
            home = next(
                n
                for n in tree.nodes.values()
                if n["repo"] == slug
                and n.get("fam")
                and any(c.get("code") and not c["children"] for c in explorer._walk(n))
            )
            descendants = list(explorer._walk(home))
            leaf = next(n for n in descendants if n.get("code") and not n["children"])
            family = home["fam"][0]
            source = leaf["code"][0]
            row = _row(f"RENAME-{node_id.upper()}-R001", "Source placement", family, slug, f"Uses `{source}`.")
        rows.append(row)
        snaps.append(Snapshot(repo=slug, slug=slug, rows=[row], files={source}))
        assert details.safe_url("requirements.md", details.Ctx(slug, family)) == (
            f"https://github.com/Knuckles-Team/{slug}/blob/HEAD/specs/{family}/requirements.md"
        )
    direct = Placer(tree).run(rows)
    placed = {r["id"]: nid for nid, rs in direct.items() for r in rs}
    assert len(placed) == 6
    assert all(tree.nodes[placed[r["id"]]]["repo"] == r["repo"] for r in rows)
    assert all(not tree.nodes[placed[r["id"]]].get("unmapped") for r in rows)
    assert not any(nid.startswith("conn.discovered." + slug) for nid in tree.nodes for slug in expected)
    assert entries["new-mcp"]["kind"] == "connector" and entries["new-mcp"]["discovered"]
    written = details.write_details(tmp_path, snaps)
    assert len(written) == 6
    for snap in snaps:
        path = tmp_path / details.detail_path(snap.repo, snap.rows[0]["family"])
        doc = json.loads(path.read_text())
        assert doc["repo"] == snap.repo and set(doc["rows"]) == {snap.rows[0]["id"]}
        assert all(f"/Knuckles-Team/{snap.slug}/" in f["url"] for f in doc["files"])


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


@pytest.mark.spec("PIPE-PAGES-R042")
def test_agent_contract_rows_land_on_the_connector_delivery_standard() -> None:
    """The agent-contract standard rows must place on a part, not fail the build as unmapped."""
    model = json.loads((PKG / "model.json").read_text())
    rows = [
        _row(
            "PIPE-CONNSPEC-R175",
            "Every repository ships one-command agent setup.",
            "connector-spec-delivery",
            "pipelines",
        ),
        _row(
            "PIPE-CONNSPEC-R176",
            "Every repository carries the standard tool-neutral AGENTS.md section.",
            "connector-spec-delivery",
            "pipelines",
        ),
        _row(
            "PIPE-CONNSPEC-R177",
            "The agent-contract check is warn-level first.",
            "connector-spec-delivery",
            "pipelines",
        ),
    ]
    direct = Placer(Tree(model)).run(rows)
    where = {r["id"]: nid for nid, rs in direct.items() for r in rs}
    assert {where[r["id"]] for r in rows} == {"pipe.connspec.std"}


# ---------------------------------------------------------------- capability search (PIPE-PAGES-R042.1 to R042.4)

_NEEDS_LAYOUT = pytest.mark.skipif(
    shutil.which("node") is None or not (PKG / "node_modules/elkjs").exists(), reason="layout engine not installed"
)
_SEARCH_ROWS = {
    "scion-sdk": [
        _row(
            "SDK-CONNECTOR-CONTROL-R030",
            "SDK provides GraphQL introspection context helpers for connector tools",
            "SDK-CONNECTOR-CONTROL",
            "scion-sdk",
        ),
        _row(
            "SDK-CONNECTOR-CONTROL-R030.1",
            "SDK owns the one GraphQL client for connectors",
            "SDK-CONNECTOR-CONTROL",
            "scion-sdk",
        ),
        _row(
            "SDK-CONNECTOR-CONTROL-R043",
            "SDK declares a source access contract for the engine client",
            "SDK-CONNECTOR-CONTROL",
            "scion-sdk",
        ),
    ],
    "adguard-home-agent": [
        _row("CONN-ADGUARD-HOME-AGENT-R002", "Shared GraphQL client", "connector-identity", "adguard-home-agent")
    ],
    "ansible-tower-mcp": [
        _row("CONN-ANSIBLE-TOWER-MCP-R002", "Shared GraphQL client", "connector-identity", "ansible-tower-mcp")
    ],
}


def _build_page(monkeypatch, tmp_path: Path, rows_by_repo: dict, aliases: dict | None = None) -> str:
    def fake_load(registry, mode, workspace=None, workers=12):
        return [
            Snapshot(
                repo=e["name"],
                slug=e["slug"],
                head="h",
                rows=rows_by_repo.get(e["name"], []),
                aliases=aliases or {} if e["name"] == "scion-sdk" else {},
            )
            for e in registry
        ]

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(explorer, "load_all", fake_load)
    page = tmp_path / "index.html"
    assert explorer.main(["--mode", "github", "--page", str(page)]) == 0
    return _with_document_mode_probe(page.read_text())


def _payload(html: str) -> dict:
    start = html.index("const PAYLOAD = ") + len("const PAYLOAD = ")
    return json.loads(html[start : html.index(";\n(function(){", start)].replace("<\\/", "</"))


def _node_search(index: dict, queries: list[str]) -> list[list[dict]]:
    """Run the page's own search module under node and return the hits for each query."""
    import subprocess

    script = (
        "const A=require('./search.cjs');const s=A.create(JSON.parse(process.argv[1]));"
        "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(q=>s.search(q))));"
    )
    out = subprocess.run(
        ["node", "-e", script, json.dumps(index), json.dumps(queries)],
        cwd=PKG,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


@pytest.mark.spec("PIPE-PAGES-R042.1")
@_NEEDS_LAYOUT
def test_search_index_covers_every_row_and_maps_it_to_a_node(monkeypatch, tmp_path: Path) -> None:
    payload = _payload(_build_page(monkeypatch, tmp_path, _SEARCH_ROWS))
    index, tree = payload["search"], payload["tree"]
    expected = {r["id"] for rows in _SEARCH_ROWS.values() for r in rows}
    assert {r[0] for r in index["rows"]} == expected == _ids(tree)
    assert len(index["rows"]) == payload["meta"]["rows"]
    holders: dict[str, str] = {}

    def walk(node: dict) -> None:
        holders.update({s["id"]: node["id"] for s in node["specs"]})
        for child in node["children"]:
            walk(child)

    walk(tree)
    for rid, title, node_idx, repo_idx, fam_idx, status_idx in index["rows"]:
        assert index["nodes"][node_idx][0] == holders[rid]
        assert index["repos"][repo_idx] and index["fams"][fam_idx] and index["st"][status_idx]
    assert len(index["nodes"]) == payload["meta"]["nodes"]
    assert all(n[1] and n[2] for n in index["nodes"])


@pytest.mark.spec("PIPE-PAGES-R042.1")
@_NEEDS_LAYOUT
def test_search_index_carries_repository_aliases(monkeypatch, tmp_path: Path) -> None:
    html = _build_page(monkeypatch, tmp_path, _SEARCH_ROWS, aliases={"OLDSDK-": "SDK-CONNECTOR-CONTROL-"})
    index = _payload(html)["search"]
    assert index["aliases"] == {"OLDSDK-": "SDK-CONNECTOR-CONTROL-"}
    (hits,) = _node_search(index, ["OLDSDK-R030.1"])
    assert hits[0]["id"] == "SDK-CONNECTOR-CONTROL-R030.1"


@pytest.mark.spec("PIPE-PAGES-R042.2")
@_NEEDS_LAYOUT
def test_a_capability_search_ranks_the_owning_row_first(monkeypatch, tmp_path: Path) -> None:
    index = _payload(_build_page(monkeypatch, tmp_path, _SEARCH_ROWS))["search"]
    (hits,) = _node_search(index, ["GraphQL client"])
    ids = [h["id"] for h in hits]
    assert ids[0] == "SDK-CONNECTOR-CONTROL-R030.1"
    assert {"CONN-ADGUARD-HOME-AGENT-R002", "SDK-CONNECTOR-CONTROL-R030"} <= set(ids[:4])
    assert hits[0]["repo"] == "scion-sdk" and hits[0]["kind"] == "row"


@pytest.mark.spec("PIPE-PAGES-R042.2")
@_NEEDS_LAYOUT
def test_an_id_search_is_exact(monkeypatch, tmp_path: Path) -> None:
    index = _payload(_build_page(monkeypatch, tmp_path, _SEARCH_ROWS))["search"]
    exact, lower, parent, prefix, nothing = _node_search(
        index,
        [
            "SDK-CONNECTOR-CONTROL-R030.1",
            "sdk-connector-control-r030.1",
            "SDK-CONNECTOR-CONTROL-R030",
            "SDK-CONNECTOR-CONTROL-R04",
            "SDK-CONNECTOR-CONTROL-R999",
        ],
    )
    assert [h["id"] for h in exact] == ["SDK-CONNECTOR-CONTROL-R030.1"]
    assert [h["id"] for h in lower] == ["SDK-CONNECTOR-CONTROL-R030.1"]
    assert [h["id"] for h in parent] == ["SDK-CONNECTOR-CONTROL-R030", "SDK-CONNECTOR-CONTROL-R030.1"]
    assert [h["id"] for h in prefix] == ["SDK-CONNECTOR-CONTROL-R043"]
    assert nothing == []


@pytest.mark.spec("PIPE-PAGES-R042.3")
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_deep_links_parse() -> None:
    import subprocess

    script = (
        "const A=require('./search.cjs');"
        "console.log(JSON.stringify(['#q=GraphQL%20client','#q=GraphQL+client&node=sdk.control.transport',"
        "'#node=conn.infra.x','#sdk.control.transport','','#q=%E0%A4%A'].map(A.parseHash)));"
        "console.log(A.hashFor('sdk.control.transport','GraphQL client'),A.hashFor('root',''));"
    )
    lines = subprocess.run(
        ["node", "-e", script], cwd=PKG, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert json.loads(lines[0]) == [
        {"node": "", "q": "GraphQL client"},
        {"node": "sdk.control.transport", "q": "GraphQL client"},
        {"node": "conn.infra.x", "q": ""},
        {"node": "sdk.control.transport", "q": ""},
        {"node": "", "q": ""},
        {"node": "", "q": "%E0%A4%A"},
    ]
    assert lines[1] == "#node=sdk.control.transport&q=GraphQL%20client "


def _with_document_mode_probe(page: str) -> str:
    assert page.startswith("<!doctype html>") and '<meta charset="utf-8">' in page
    probe = """<script>
document.documentElement.dataset.documentMode=document.compatMode;
document.documentElement.dataset.documentCharset=document.characterSet;
</script>"""
    return page.replace("</body>", probe + "</body>")


def _assert_browser_document(output: str) -> None:
    assert 'data-document-mode="CSS1Compat"' in output
    assert 'data-document-charset="UTF-8"' in output


def _chrome() -> str | None:
    import glob

    for pattern in (
        "/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        str(
            Path.home()
            / ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"
        ),
    ):
        found = sorted(glob.glob(pattern))
        if found:
            return found[-1]
    return shutil.which("chromium") or shutil.which("google-chrome")


@pytest.mark.spec("PIPE-PAGES-R042.4")
@_NEEDS_LAYOUT
@pytest.mark.skipif(_chrome() is None, reason="no headless Chromium available")
def test_a_q_deep_link_lands_on_the_owning_part_in_a_browser(monkeypatch, tmp_path: Path) -> None:
    import subprocess

    page = tmp_path / "index.html"
    page.write_text(_build_page(monkeypatch, tmp_path, _SEARCH_ROWS))
    out = subprocess.run(
        [
            _chrome(),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--host-resolver-rules=MAP * ~NOTFOUND",
            "--window-size=1500,950",
            "--virtual-time-budget=6000",
            "--dump-dom",
            page.as_uri() + "#q=GraphQL%20client",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout
    _assert_browser_document(out)
    assert re.search(r'<li data-spec="SDK-CONNECTOR-CONTROL-R030.1" class="flash"', out)
    assert 'role="combobox"' in out and 'aria-label="Search results"' in out
    assert re.search(r'<input id="q"[^>]*>', out) and "GraphQL client" in out


@pytest.mark.spec("PIPE-PAGES-R042.5")
def test_the_map_fills_the_viewport_with_full_screen_and_panel_toggle() -> None:
    """PIPE-PAGES-R042.5: no page width cap, the map fills the viewport height, wide overview."""
    html = (ROOT / "scripts/architecture_explorer/template.html").read_text()
    assert "max-width:1880px" not in html
    assert ".app{display:flex;flex-direction:column;height:100vh;height:100dvh;" in html
    assert "calc(100vh - 150px)" not in html
    assert 'id="zfull"' in html and "requestFullscreen" in html and ".canvas:fullscreen" in html
    assert 'id="zpanel"' in html and "main.work.nopanel" in html
    assert 'if(n.id==="root") ctx.fillRect(0,sy,W,sh)' in html
    fixed = json.loads((ROOT / "scripts/architecture_explorer/model.json").read_text())["fixed_layout"]
    assert fixed["w"] / fixed["h"] >= 1.6


@pytest.mark.spec("PIPE-PAGES-R042")
def test_webui_composed_acceptance_row_places_on_its_part_not_the_allowlist() -> None:
    """WEBUI-APPS-R050 failed every publish as unmapped; it must place on the acceptance part."""
    model = json.loads((PKG / "model.json").read_text())
    row = _row(
        "WEBUI-APPS-R050",
        "Composed deployment and shared-backend acceptance.",
        "arbora-app-surface",
        "overstory",
        "Qualify the installed WebUI with real Arbora served operations.",
    )
    tree = Tree(model)
    direct = Placer(tree).run([row])
    where = {r["id"]: nid for nid, rs in direct.items() for r in rs}
    assert where["WEBUI-APPS-R050"] == "webui.apps.accept"
    assert unmapped_violations(tree, direct, []) == []
    assert model["unmapped_allow"] == []


# ------------------------------------------------------------- spec details (PIPE-PAGES-R042.6 to R042.8)

FULL_TEXT = "Zq-FULLTEXT-MARKER " + "The long tail of the requirement stays out of the page. " * 40
REQ_MD = (
    "# FAM requirements\n\n| ID | Requirement | Verification |\n|---|---|---|\n"
    "| `FAM-R001` | **Solver certificate.** Emit a signed certificate for every solve. " + FULL_TEXT + " "
    "| A fixture proves the `certificate` field; see [the plan](plan.md) and [site](https://example.org/x). |\n"
    "| `FAM-R002` | Plain row without a bold lead that explains itself in one line. Second sentence. | Checked by hand. |\n"
)
PLAN_MD = "# Plan\n\nDesign notes.\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\ncode <b>x</b>\n```\n"
TEST_MD = "| ID | Requirement | Test |\n|---|---|---|\n| P-1 | FAM-R001 | Certificate is signed. |\n| P-2 | FAM-R001.1 | Other row. |\n"


def _detail_snapshots(with_plan: bool = True) -> list[Snapshot]:
    def rows_for(repo: str) -> list[dict]:
        out = []
        for rid, title in (("FAM-R001", "Solver certificate"), ("FAM-R002", "Plain row")):
            body = requirement_text(REQ_MD)[rid]
            row = _row(rid, title, family="fam", repo=repo, text=body)
            row["desc"] = details.describe(details.row_parts(body)[0], title)
            row.update(
                landed_in=["abcdef123456"],
                verified_by=["tests/test_x.py:12", "../escape.py:1"],
                rollup_of=["FAM-R001.1"],
            )
            out.append(row)
        return out

    docs = (
        {"plan.md": PLAN_MD, "test-spec.md": TEST_MD, "architecture.md": "# Arch\n\nBoxes."}
        if with_plan
        else {"test-spec.md": TEST_MD}
    )
    return [
        Snapshot(
            repo=e["name"],
            slug=e["slug"],
            head="h",
            files={"specs/fam/requirements.md", "specs/fam/plan.md"} if e["name"] == "pipelines" else set(),
            rows=rows_for(e["name"]) if e["name"] == "pipelines" else [],
            docs={"fam": docs} if e["name"] == "pipelines" else {},
        )
        for e in json.loads((PKG / "registry.json").read_text())["repositories"]
    ]


def _build_with_details(monkeypatch, tmp_path: Path, snaps: list[Snapshot]) -> Path:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(explorer, "load_all", lambda registry, mode, workspace=None, workers=12: snaps)
    page = tmp_path / "architecture" / "index.html"
    assert explorer.main(["--mode", "github", "--page", str(page)]) in (0, 1)
    page.write_text(_with_document_mode_probe(page.read_text()))
    return page


@pytest.mark.spec("PIPE-PAGES-R042.6")
def test_description_is_the_first_plain_sentence_capped_at_160() -> None:
    assert (
        details.describe("Emit a **signed** `certificate` per solve. Another sentence.")
        == "Emit a signed certificate per solve."
    )
    # A bold lead that repeats the title is skipped; a different lead stays.
    assert (
        details.describe("**Solver certificate.** Emit one per solve. More.", "Solver certificate")
        == "Emit one per solve."
    )
    assert details.describe("**Other lead.** Body sentence.", "Title") == "Other lead."
    # Links keep their label only, and a long sentence is cut on a word with an ellipsis.
    assert details.describe("See [the plan](plan.md) for it.") == "See the plan for it."
    long = details.describe("word " * 80)
    assert len(long) <= details.DESC_MAX and long.endswith("…")
    assert details.describe("") == ""
    # Pipes inside code spans stay in their cell; the second cell is the acceptance text.
    assert details.row_parts(" Use `a | b` here. | Check it. |") == ("Use `a | b` here.", "Check it.")


@pytest.mark.spec("PIPE-PAGES-R042.6")
@_NEEDS_LAYOUT
def test_page_rows_carry_desc_and_never_the_full_text(monkeypatch, tmp_path: Path) -> None:
    page = _build_with_details(monkeypatch, tmp_path, _detail_snapshots())
    html = page.read_text()
    assert "Zq-FULLTEXT-MARKER" not in html
    payload = _payload(html)
    rows = {}

    def walk(node: dict) -> None:
        rows.update({s["id"]: s for s in node["specs"]})
        for child in node["children"]:
            walk(child)

    walk(payload["tree"])
    assert rows["FAM-R001"]["desc"].startswith("Emit a signed certificate for every solve.")
    assert len(rows["FAM-R001"]["desc"]) <= details.DESC_MAX
    assert rows["FAM-R002"]["desc"] == "Plain row without a bold lead that explains itself in one line."


@pytest.mark.spec("PIPE-PAGES-R042.7")
@_NEEDS_LAYOUT
def test_one_family_json_is_written_per_family_with_full_row_detail(monkeypatch, tmp_path: Path) -> None:
    page = _build_with_details(monkeypatch, tmp_path, _detail_snapshots())
    files = sorted(p.relative_to(page.parent).as_posix() for p in (page.parent / "spec-details").rglob("*.json"))
    assert files == ["spec-details/pipelines/fam.json"]
    doc = json.loads((page.parent / files[0]).read_text())
    row = doc["rows"]["FAM-R001"]
    assert "Zq-FULLTEXT-MARKER" in row["req"] and "<script" not in row["req"]
    assert "certificate" in row["acc"] and "https://example.org/x" in row["acc"]
    assert "https://github.com/Knuckles-Team/pipelines/blob/HEAD/specs/fam/plan.md" in row["acc"]
    assert row["landed_in"] == [
        {"label": "abcdef123456", "url": "https://github.com/Knuckles-Team/pipelines/commit/abcdef123456"}
    ]
    assert row["verified_by"][0]["url"] == "https://github.com/Knuckles-Team/pipelines/blob/HEAD/tests/test_x.py#L12"
    assert row["verified_by"][1]["url"] == ""  # a path that leaves the repository is not linked
    assert row["rollup_of"] == ["FAM-R001.1"]
    assert len(row["tests"]) == 1 and "Certificate is signed." in row["tests"][0]  # R001.1 is another row
    assert [d["label"] for d in doc["docs"]] == ["Plan", "Design: architecture", "Test spec"]
    plan = next(d for d in doc["docs"] if d["name"] == "plan.md")
    assert (
        "<h3>Plan</h3>" in plan["html"]
        and "<li>one</li>" in plan["html"]
        and '<div class="tbl"><table>' in plan["html"]
    )
    assert "code &lt;b&gt;x&lt;/b&gt;" in plan["html"]
    assert {f["name"] for f in doc["files"]} == {"requirements.md", "plan.md", "architecture.md", "test-spec.md"}
    # A rebuild with the family gone removes its file.
    snaps = _detail_snapshots()
    snaps[[s.repo for s in snaps].index("pipelines")].rows = []
    _build_with_details(monkeypatch, tmp_path, snaps)
    assert not list((page.parent / "spec-details").rglob("*.json"))


@pytest.mark.spec("PIPE-PAGES-R042.7")
@_NEEDS_LAYOUT
def test_a_row_whose_family_has_no_plan_still_gets_detail(monkeypatch, tmp_path: Path) -> None:
    page = _build_with_details(monkeypatch, tmp_path, _detail_snapshots(with_plan=False))
    doc = json.loads((page.parent / "spec-details/pipelines/fam.json").read_text())
    assert [d["name"] for d in doc["docs"]] == ["test-spec.md"]
    assert "Zq-FULLTEXT-MARKER" in doc["rows"]["FAM-R001"]["req"]
    assert "tests" not in doc["rows"]["FAM-R002"] and "acc" in doc["rows"]["FAM-R002"]
    bare = details.family_detail(
        "pipelines", "pipelines", "none", [_row("N-R001", "No files", family="none")], {}, set()
    )
    assert bare["docs"] == [] and bare["rows"]["N-R001"]["req"] == "" and bare["files"][0]["name"] == "requirements.md"


@pytest.mark.spec("PIPE-PAGES-R042.8")
def test_markdown_escapes_raw_html_and_drops_unsafe_links() -> None:
    ctx = details.Ctx("pipelines", "fam")
    out = details.render_markdown(
        "<script>alert(1)</script>\n\n"
        "Text <img src=x onerror=alert(1)> and **<b>bold</b>**.\n\n"
        "[bad](javascript:alert(1)) [data](data:text/html,x) [proto](//evil.example/x) [up](../../../etc/passwd) "
        "[ok](https://example.org/a?b=1&c=2) [rel](../other/plan.md#top) [anchor](#x)\n\n"
        "- <iframe src=//x></iframe>\n\n"
        "| h<script> |\n|---|\n| <svg onload=alert(1)> |\n\n"
        "```html\n<script>alert(2)</script>\n```\n\n"
        "> <style>x{}</style>\n\n`<script>`\n",
        ctx,
    )
    assert (
        "<script" not in out
        and "<img" not in out
        and "<iframe" not in out
        and "<svg" not in out
        and "<style" not in out
    )
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out and "&lt;script&gt;alert(2)&lt;/script&gt;" in out
    assert "onerror=alert(1)&gt;" in out  # the attribute text is inert text, not a tag
    hrefs = re.findall(r'href="([^"]*)"', out)
    assert hrefs == [
        "https://example.org/a?b=1&amp;c=2",
        "https://github.com/Knuckles-Team/pipelines/blob/HEAD/specs/other/plan.md#top",
    ]
    assert "javascript:" not in " ".join(hrefs) and "bad</a>" not in out and ">bad<" not in out.replace("bad ", "")
    # A script inside a spec file reaches the family JSON escaped as well.
    row = _row("FAM-R9", "t", text=" <script>alert(3)</script> | <script>alert(4)</script> |")
    doc = details.family_detail("r", "r", "fam", [row], {"plan.md": "<script>alert(5)</script>"}, set())
    assert "<script" not in json.dumps(doc) and "&lt;script&gt;alert(5)" in doc["docs"][0]["html"]


@pytest.mark.spec("PIPE-PAGES-R042.8")
def test_page_never_assigns_markup_and_exposes_the_expand_controls() -> None:
    html = (PKG / "template.html").read_text()
    assert "innerHTML" not in html and "insertAdjacentHTML" not in html and "document.write" not in html
    for needle in (
        '"aria-expanded"',
        "Expand all shown",
        "Collapse all",
        "spec-details/",
        "new DOMParser()",
        "DET_TAGS",
    ):
        assert needle in html
    # Wide tables and code scroll in their own block; the expanded body may not widen the page.
    assert ".xbody .md .tbl{overflow-x:auto" in html and ".xbody .md pre{overflow-x:auto" in html
    assert ".specs .de{" in html and "-webkit-line-clamp:2" in html


@pytest.mark.spec("PIPE-PAGES-R042.6")
@_NEEDS_LAYOUT
def test_page_size_grows_by_a_bounded_amount_per_row(monkeypatch, tmp_path: Path) -> None:
    """Measure the page with and without descriptions: the growth per row stays within the description cap."""
    snaps = _detail_snapshots()
    with_desc = len(_build_with_details(monkeypatch, tmp_path / "a", snaps).read_bytes())
    for snap in snaps:
        for row in snap.rows:
            row["desc"] = ""
    without = len(_build_with_details(monkeypatch, tmp_path / "b", snaps).read_bytes())
    rows = sum(len(s.rows) for s in snaps)
    growth = with_desc - without
    assert 0 < growth <= rows * (details.DESC_MAX + 16), f"{rows} rows: {without} -> {with_desc} bytes (+{growth})"
    assert with_desc - without < 0.1 * without


@pytest.mark.spec("PIPE-PAGES-R042.6")
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_search_matches_a_description_only_after_title_and_id_matches() -> None:
    import subprocess

    index = {
        "v": 1,
        "repos": ["r"],
        "fams": ["f"],
        "st": ["VERIFIED"],
        "nodes": [["n", "Node", "Part.", 0, []]],
        "rows": [["A-R001", "Plain title", 0, 0, 0, 0], ["A-R002", "Quartz engine", 0, 0, 0, 0]],
        "aliases": {},
    }
    script = (
        "const A=require('./search.cjs');const ix=JSON.parse(process.argv[1]);"
        "const d={'A-R001':'Uses the quartz crystal oscillator.'};"
        "const a=A.create(ix,id=>d[id]).search('quartz').map(h=>h.id);const b=A.create(ix).search('quartz').map(h=>h.id);"
        "console.log(JSON.stringify([a,b]));"
    )
    out = subprocess.run(["node", "-e", script, json.dumps(index)], cwd=PKG, capture_output=True, text=True, check=True)
    with_desc, without = json.loads(out.stdout)
    assert with_desc == ["A-R002", "A-R001"] and without == ["A-R002"]


@pytest.mark.spec("PIPE-PAGES-R042.7")
@_NEEDS_LAYOUT
@pytest.mark.skipif(_chrome() is None, reason="no headless Chromium available")
def test_expanding_a_row_fetches_its_family_once_and_renders_it_safely(monkeypatch, tmp_path: Path) -> None:
    import functools
    import http.server
    import subprocess
    import threading

    page = _build_with_details(monkeypatch, tmp_path, _detail_snapshots())
    hook = (
        "<script>setTimeout(()=>{const b=document.querySelector('[data-spec=\"FAM-R001\"] button.ti');if(b)b.click();},800);"
        "setTimeout(()=>{const d=document.querySelector('[data-spec=\"FAM-R001\"] details');if(d)d.open=true;},1800);</script></body>"
    )
    page.write_text(page.read_text().replace("</body>", hook))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(page.parent))
    handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = subprocess.run(
            [
                _chrome(),
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--window-size=1500,950",
                "--virtual-time-budget=8000",
                "--dump-dom",
                f"http://127.0.0.1:{server.server_port}/index.html#q=FAM-R001",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout
        _assert_browser_document(out)
    finally:
        server.shutdown()
    li = out[out.index('data-spec="FAM-R001"') :]
    assert 'aria-expanded="true"' in li[:1200] and 'class="xbody"' in li
    assert "Zq-FULLTEXT-MARKER" in li and "landed_in" in li and "Plan (plan.md)" in li and "<h3>Plan</h3>" in li
    assert li.count('class="xbody"') >= 1 and "Expand all shown" in out and "Collapse all" in out


@pytest.mark.spec("PIPE-PAGES-R042.9")
def test_every_registered_repository_has_a_part_and_its_rows_place_without_the_allowlist() -> None:
    """A registry repository with specs needs a part that owns it, and its rows land there, not in Unmapped."""
    model = json.loads((PKG / "model.json").read_text())
    registry = json.loads((PKG / "registry.json").read_text())
    tree = Tree(model)
    owned = {n["repo"] for n in tree.nodes.values() if n["repo"] and not n.get("external")}
    assert {e["name"] for e in registry["repositories"]} <= owned
    rows = [
        _row("SG-CONTENT-R001", "Catalog content", family="catalog-content", repo="skill-graphs"),
        _row("SG-CONTENT-R001.3", "Served through the convention", family="catalog-content", repo="skill-graphs"),
    ]
    direct = Placer(tree).run(rows)
    where = {r["id"]: nid for nid, rs in direct.items() for r in rs}
    assert set(where.values()) == {"skills.graphs"}
    assert tree.nodes["skills.graphs"]["label"] == "Skill graphs" and tree.nodes["skills.graphs"]["level"] > 0
    assert unmapped_violations(tree, direct, model.get("unmapped_allow", [])) == []
    assert registry["pages_node"]["skill-graphs"] == "skills"


_GUIDE = "https://github.com/Knuckles-Team/.github/blob/main/CONTRIBUTING.md"
_FRONT_DOOR = "https://knuckles-team.github.io/.github/"


@pytest.mark.spec("PIPE-PAGES-R042.10")
@_NEEDS_LAYOUT
def test_footer_links_the_guide_and_front_door_and_only_specified_rows_point_to_the_guide(
    monkeypatch, tmp_path: Path
) -> None:
    import functools
    import http.server
    import subprocess
    import threading

    snaps = _detail_snapshots()
    for snap in snaps:
        for row in snap.rows:
            if row["id"] == "FAM-R002":
                row["status"] = "VERIFIED"
    page = _build_with_details(monkeypatch, tmp_path, snaps)
    html = page.read_text()
    foot = html[html.index('id="note"') : html.index('id="foot"')]
    assert f'href="{_GUIDE}"' in foot and f'href="{_FRONT_DOOR}"' in foot and "at least every 30 minutes" in foot
    head = html[html.index("<header") : html.index("</header>")]
    assert "CONTRIBUTING.md" not in head and _FRONT_DOOR not in head
    hook = (
        "<script>setTimeout(()=>{document.querySelectorAll('button.ti').forEach(b=>b.click());},800);</script></body>"
    )
    page.write_text(html.replace("</body>", hook))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(page.parent))
    handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = subprocess.run(
            [
                _chrome(),
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--window-size=1500,950",
                "--virtual-time-budget=8000",
                "--dump-dom",
                f"http://127.0.0.1:{server.server_port}/index.html#q=FAM-R",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout
        _assert_browser_document(out)
    finally:
        server.shutdown()
    specified = out[out.index('data-spec="FAM-R001"') : out.index('data-spec="FAM-R002"')]
    verified = out[out.index('data-spec="FAM-R002"') :]
    verified = verified[: verified.find("</ul>")]
    assert "Open work. To pick it up" in specified and _GUIDE in specified and "/tree/HEAD/specs/fam" in specified
    assert "Open work" not in verified and _GUIDE not in verified


@pytest.mark.spec("PIPE-PAGES-R042.11")
def test_contribution_path_is_in_the_page_head_details_and_llms_txt() -> None:
    head = explorer.DOC_HEAD
    assert f'<link rel="help" href="{_GUIDE}">' in head and f'<link rel="start" href="{_FRONT_DOOR}">' in head
    assert '<meta name="description"' in head and _FRONT_DOOR in head[head.index('<meta name="description"') :]
    html = (explorer.HERE / "template.html").read_text()
    block = html[html.index('<details class="contribute"') : html.index("</details>", html.index('class="contribute"'))]
    assert " open" not in block.split(">", 1)[0]
    assert "How to contribute (for people and agents)" in block and block.count("<li>") == 5
    assert html.index('id="foot"') < html.index('class="contribute"')
    for url in (explorer.FRONT_DOOR, explorer.CONTRIBUTING, explorer.ARBORA_DEVELOPMENT):
        assert url in block
    assert (explorer.FRONT_DOOR, explorer.CONTRIBUTING) == (_FRONT_DOOR, _GUIDE)
    assert explorer.EXPLORER == explorer.CANONICAL
    shape = details.detail_path("REPO", "FAM").replace("REPO", "<repo>").replace("FAM", "<family>")
    assert explorer.DETAILS_PATTERN == explorer.CANONICAL + shape
    llms = explorer.llms_txt()
    assert _FRONT_DOOR in llms and _GUIDE in llms and explorer.SKILLS in llms and explorer.DETAILS_PATTERN in llms
    assert all(f"{i}. " in llms for i in range(1, 6))


@pytest.mark.spec("PIPE-PAGES-R042.11")
@_NEEDS_LAYOUT
def test_a_build_writes_llms_txt_beside_the_page(monkeypatch, tmp_path: Path) -> None:
    page = _build_with_details(monkeypatch, tmp_path, _detail_snapshots())
    assert (page.parent / "llms.txt").read_text() == explorer.llms_txt()
    assert _FRONT_DOOR in (page.parent / "llms.txt").read_text() and 'rel="start"' in page.read_text()


@pytest.mark.spec("PIPE-PAGES-R042")
def test_tuig_preserves_identity_and_distinguishes_planned_runtime() -> None:
    model = json.loads((PKG / "model.json").read_text())
    terminal = next(node for node in model["children"] if node["id"] == "tui")
    assert terminal["label"] == "Tuig"
    assert terminal["repo"] == "tuig"
    assert terminal["role"] == "TUI / CLI"
    assert terminal["desc"].startswith("tuig is the single Rust/Ratatui CLI")
    assert ["tui", "arbora", "A2A / REST"] in model["edges"]
    edge = next(edge for edge in model["fixed_layout"]["edges"] if edge["from"] == "tui")
    assert (edge["to"], edge["label"]) == ("arbora", "A2A / REST")
    children = {node["id"]: node for node in terminal["children"]}
    assert set(children) == {
        "tui.quality",
        "tui.client",
        "tui.chat",
        "tui.native",
        "tui.coding",
        "tui.tasks",
        "tui.screens",
    }
    assert "planned" in children["tui.coding"]["role"]
    assert "planned" in children["tui.chat"]["desc"]
    assert "not delivered" in children["tui.client"]["desc"]
    assert ["tui.coding", "tui.client", "planned operations"] in terminal["edges"]
    assert all(
        not path.startswith("agent_terminal_ui")
        for node in [terminal, *children.values()]
        for path in node.get("code", [])
    )


@pytest.mark.spec("PIPE-PAGES-R042")
@_NEEDS_LAYOUT
def test_display_brands_survive_generation_without_renaming_repositories(monkeypatch, tmp_path: Path) -> None:
    payload = _payload(_build_page(monkeypatch, tmp_path, {}))
    nodes = {node["id"]: node for node in payload["tree"]["children"]}
    brands = {
        "webui": ("Overstory", "overstory"),
        "tui": ("Tuig", "tuig"),
        "sdk": ("Scion", "scion-sdk"),
        "au": ("Meristem", "meristem"),
        "geniusbot": ("Axil", "axil"),
    }
    for node_id, (label, repo) in brands.items():
        assert (nodes[node_id]["label"], nodes[node_id]["repo"]) == (label, repo)
    assert payload["tree"]["label"] == "Arbora Ecosystem"
    assert nodes["eg"]["label"] == "Medulla"
    assert nodes["egserver"]["label"] == "Medulla Stem"
    assert nodes["arbora"]["label"] == "Arbora"
    assert nodes["geniusbot"]["role"] == "Desktop GUI"
    assert nodes["au"]["role"] == "Agent Harness"
    assert nodes["sdk"]["role"] == "Connector SDK"
    assert nodes["skills"]["label"] == "Universal Skills"
    assert nodes["skills"]["role"] == "Agent Skills"
    assert nodes["sources"]["label"] == "Source Systems"


_AXIL_PARTS = {
    "backend": (1, 2, 3, 5),
    "lifecycle": (4, 8, 10),
    "approvals": (6,),
    "terminal": (7,),
    "panels": (9, 11, 14),
    "packaging": (12,),
    "tokens": (13,),
    "docs": (15, 16, 17, 18),
    "runs": (19,),
    "quality": (20,),
}


@pytest.mark.spec("PIPE-PAGES-R042")
def test_axil_parts_place_existing_roots_and_descendants_once_without_guessing() -> None:
    model = json.loads((PKG / "model.json").read_text())
    tree = Tree(model)
    desktop = tree.nodes["geniusbot"]
    assert (desktop["repo"], desktop["fam"]) == ("axil", ["desktop-client"])
    expected = {
        f"GENIUSBOT-CLIENT-R{number:03d}{suffix}": f"geniusbot.{part}"
        for part, numbers in _AXIL_PARTS.items()
        for number in numbers
        for suffix in ("", ".1", ".1.1")
    }
    rows = [_row(rid, "Requirement", "desktop-client", "axil") for rid in expected]
    unknown = [
        _row(rid, "Requirement", "desktop-client", "axil")
        for rid in ("GENIUSBOT-CLIENT-R021", "GENIUSBOT-CLIENT-R0010")
    ]
    direct = Placer(tree).run(rows + unknown)
    placed = [(row["id"], nid) for nid, entries in direct.items() for row in entries]
    assert len(placed) == len(rows + unknown)
    assert dict(placed) == {**expected, **{row["id"]: "geniusbot.unmapped" for row in unknown}}
    assert all(tree.nodes[nid]["repo"] == "axil" for nid in expected.values())


@pytest.mark.spec("PIPE-PAGES-R042")
@_NEEDS_LAYOUT
def test_axil_parts_survive_generation_without_changing_rows_or_statuses(monkeypatch, tmp_path: Path) -> None:
    rows = [
        {**_row(f"GENIUSBOT-CLIENT-R{number:03d}", "Requirement", "desktop-client", "axil"), "status": status}
        for number, status in zip(range(1, 21), ("VERIFIED", "LANDED", "SPECIFIED", "RETIRED") * 5)
    ]
    payload = _payload(_build_page(monkeypatch, tmp_path, {"axil": rows}))
    desktop = next(node for node in payload["tree"]["children"] if node["id"] == "geniusbot")
    assert {node["id"] for node in desktop["children"]} == {f"geniusbot.{part}" for part in _AXIL_PARTS}
    assert desktop["specs"] == []
    assert "layout" in desktop
    emitted = [row for node in desktop["children"] for row in node["specs"]]
    assert len(emitted) == len(rows)
    assert {(row["id"], row["status"], row["repo"], row["family"]) for row in emitted} == {
        (row["id"], row["status"], row["repo"], row["family"]) for row in rows
    }


@pytest.mark.spec("PIPE-PAGES-R042")
@_NEEDS_LAYOUT
@pytest.mark.skipif(_chrome() is None, reason="no headless Chromium available")
@pytest.mark.parametrize("viewport", ["1440,1000", "390,844"])
def test_ocean_browser_keyboard_zoom_pan_search_and_camera_history(monkeypatch, tmp_path: Path, viewport: str) -> None:
    """Exercise real DOM/canvas controls without introducing a browser framework."""
    import subprocess

    page = tmp_path / "index.html"
    # Use the actual reduced-motion code path, avoiding animation timing in CLI Chrome.
    preferences = """<script>
const nativeMatchMedia=window.matchMedia.bind(window);
window.matchMedia=q=>q==='(prefers-reduced-motion: reduce)'
  ? {matches:true,addEventListener(){},removeEventListener(){}} : nativeMatchMedia(q);
</script>"""
    probe = """<script>
setTimeout(async()=>{
  const result=document.createElement('output'); result.id='interaction-result';
  const check=(ok,name)=>{if(!ok)throw Error(name);};
  const key=(target,value)=>target.dispatchEvent(new KeyboardEvent('keydown',{key:value,bubbles:true,cancelable:true}));
  try{
    const a=window.__arch, cv=document.getElementById('cv'), get=id=>document.getElementById(id);
    const initial={...a.cam}; get('zin').click(); get('zin').click();
    check(a.cam.k>initial.k,'repeated zoom in'); get('zout').click();
    check(a.cam.k>initial.k,'zoom out preserves intermediate scale');
    cv.focus(); check(document.activeElement===cv,'canvas keyboard focus');
    const beforePan=a.cam.x; key(cv,'ArrowRight'); check(a.cam.x>beforePan,'keyboard pan');
    const beforeWheel=a.cam.k; cv.dispatchEvent(new WheelEvent('wheel',{deltaY:-100,cancelable:true}));
    check(a.cam.k>beforeWheel,'wheel zoom');
    const beforeGo={...a.cam}; a.go('webui',{instant:true}); get('back').click();
    check(Math.abs(a.cam.k-beforeGo.k)<0.000001 && a.cam.x===beforeGo.x,'camera back history');
    get('zpanel').click(); check(get('zpanel').getAttribute('aria-pressed')==='true','panel hide');
    get('zpanel').click(); check(get('zpanel').getAttribute('aria-pressed')==='false','panel restore');
    key(document.body,'/'); const q=get('q'); check(document.activeElement===q,'search shortcut');
    q.value='GraphQL client'; q.dispatchEvent(new Event('input',{bubbles:true}));
    check(q.getAttribute('aria-expanded')==='true' && a.hits.length>0,'search results');
    key(q,'ArrowDown'); key(q,'ArrowUp'); key(q,'Enter');
    check(get('results').hidden && location.hash.includes('q=GraphQL'),'search selection deep link');
    q.focus(); key(q,'Escape'); check(get('results').hidden,'search Escape');
    const theme=document.documentElement.getAttribute('data-theme'); get('theme').click();
    check(document.documentElement.getAttribute('data-theme')!==theme,'theme switch');
    check(getComputedStyle(cv).transitionDuration==='0s','reduced motion');
    check(get('ocean-motion').disabled && document.documentElement.dataset.oceanMotion==='paused','reduced-motion wallpaper off');
    check(document.documentElement.scrollWidth<=innerWidth,'no horizontal page overflow');
    result.textContent='PASS';
  }catch(error){result.textContent='FAIL: '+error.message;}
  document.body.append(result);
},500);
</script>"""
    page.write_text(
        _build_page(monkeypatch, tmp_path, _SEARCH_ROWS)
        .replace("</head>", preferences + "</head>")
        .replace("</body>", probe + "</body>")
    )
    out = subprocess.run(
        [
            _chrome(),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--host-resolver-rules=MAP * ~NOTFOUND",
            f"--window-size={viewport}",
            "--virtual-time-budget=6000",
            "--dump-dom",
            page.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout
    _assert_browser_document(out)
    assert '<output id="interaction-result">PASS</output>' in out, out[-1500:]


@pytest.mark.spec("PIPE-PAGES-R042")
def test_explorer_display_names_preserve_existing_knowledge_and_dashboard_identity() -> None:
    tree = Tree(json.loads((PKG / "model.json").read_text()))
    studio = tree.nodes["webui.dash"]
    assert studio["label"] == "Overstory Studio"
    assert studio["fam"] == ["agent-dashboards"]
    assert studio["code"] == ["src/components/dashboards", "src/lib/dashboards"]
    knowledge = tree.nodes["webui.apps.graph"]
    assert "Understory" in knowledge["desc"]
    assert "Graph edits go through the engine." in knowledge["desc"]
    assert "src/components/atlas" in knowledge["code"]
    assert tree.nodes["au"]["label"] == "Meristem"
    assert tree.nodes["au"]["repo"] == "meristem"
    terminal = tree.nodes["tui"]["desc"]
    assert "bounded local ACP text sessions" in terminal
    assert "Installed backend and release qualification" in terminal
    assert "durable resume and central continuation remain separate gates" in terminal
    assert "Approval attachment and durable resume are not delivered" in tree.nodes["tui.coding"]["desc"]


@pytest.mark.spec("PIPE-PAGES-R042")
@_NEEDS_LAYOUT
@pytest.mark.skipif(_chrome() is None, reason="no headless Chromium available")
def test_ocean_browser_motion_controls_and_composited_wave_phases(monkeypatch, tmp_path: Path) -> None:
    """Validate real CSS animation phases and accessibility without a video simulation."""
    import subprocess

    page = tmp_path / "motion.html"
    probe = """<script>
setTimeout(()=>{
  const result=document.createElement('output'); result.id='motion-result';
  const check=(ok,name)=>{if(!ok)throw Error(name);};
  try{
    const root=document.documentElement, button=document.getElementById('ocean-motion');
    if(sessionStorage.getItem('ocean-reload-proof')==='pending'){
      check(root.dataset.oceanMotion==='paused' && button.getAttribute('aria-pressed')==='false','opt out restored after real reload');
      check(localStorage.getItem('arbora-arch-ocean-motion')==='off','persisted opt out survives reload');
      button.click(); sessionStorage.removeItem('ocean-reload-proof');
      result.textContent='PASS'; document.body.append(result); return;
    }
    const waves=[...document.querySelectorAll('.ocean-wave')];
    check(root.dataset.oceanMotion==='running','default motion on');
    check(waves.length===3,'three shared waves');
    const animations=waves.map(w=>w.getAnimations()[0]);
    check(animations.every(a=>a&&a.playState==='running'),'CSS animations running');
    animations.forEach(a=>{a.currentTime=0;});
    const before=waves.map(w=>getComputedStyle(w).transform);
    animations.forEach(a=>{a.currentTime=12000;});
    check(waves.every((w,i)=>getComputedStyle(w).transform!==before[i]),'distinct real rendered phases');
    button.click(); check(root.dataset.oceanMotion==='paused','opt out pauses');
    check(waves.every(w=>getComputedStyle(w).animationPlayState==='paused'),'CSS animations paused');
    check(localStorage.getItem('arbora-arch-ocean-motion')==='off','opt out persisted');
    check(button.getAttribute('aria-pressed')==='false','accessible state');
    button.click(); check(root.dataset.oceanMotion==='running','resume');
    Object.defineProperty(document,'hidden',{configurable:true,value:true});
    document.dispatchEvent(new Event('visibilitychange'));
    check(root.dataset.oceanMotion==='paused','hidden page pauses');
    Object.defineProperty(document,'hidden',{configurable:true,value:false});
    document.dispatchEvent(new Event('visibilitychange'));
    check(root.dataset.oceanMotion==='running','visible page resumes');
    check(getComputedStyle(document.querySelector('.ocean-scene')).pointerEvents==='none','wallpaper never intercepts input');
    button.click(); sessionStorage.setItem('ocean-reload-proof','pending');
    location.reload(); return;
  }catch(error){result.textContent='FAIL: '+error.message;}
  document.body.append(result);
},500);
</script>"""
    page.write_text(_build_page(monkeypatch, tmp_path, _SEARCH_ROWS).replace("</body>", probe + "</body>"))
    out = subprocess.run(
        [
            _chrome(),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--virtual-time-budget=6000",
            "--dump-dom",
            page.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout
    _assert_browser_document(out)
    assert '<output id="motion-result">PASS</output>' in out, out[-1500:]


@pytest.mark.spec("PIPE-PAGES-R042")
@_NEEDS_LAYOUT
@pytest.mark.skipif(_chrome() is None, reason="no headless Chromium available")
def test_ocean_browser_candidate_model_subtitles_paint_without_overlap(monkeypatch, tmp_path: Path) -> None:
    """Actual candidate-model fixture, explicitly not the live-payload visual snapshot."""
    import os
    import subprocess

    page = tmp_path / "candidate-model-fixture.html"
    spy = """<script>
window.__paint=[];
const originalFillText=CanvasRenderingContext2D.prototype.fillText;
const originalClear=CanvasRenderingContext2D.prototype.clearRect;
CanvasRenderingContext2D.prototype.clearRect=function(...args){window.__paint=[];return originalClear.apply(this,args);};
CanvasRenderingContext2D.prototype.fillText=function(text,x,y,...rest){
 const m=this.measureText(text);window.__paint.push({text,x,y,font:this.font,top:y-m.actualBoundingBoxAscent,bottom:y+m.actualBoundingBoxDescent});
 return originalFillText.call(this,text,x,y,...rest);
};
</script>"""
    probe = """<script>
setTimeout(async()=>{
 await document.fonts.ready;
 const result=document.createElement('output');result.id='subtitle-result';
 try{
  const check=(ok,name)=>{if(!ok)throw Error(name);}, a=window.__arch;
  check(a.selected==='root','normal root camera');
  const evidence=[];
  for(const [id,label,role] of [['sdk','Scion','Connector SDK'],['au','Meristem','Agent Harness'],['skills','Universal Skills','Agent Skills']]){
   const r=a.rect(id), x=(r[0]-a.cam.x)*a.cam.k, y=(r[1]-a.cam.y)*a.cam.k, w=r[2]*a.cam.k,h=r[3]*a.cam.k;
   const title=window.__paint.find(p=>p.text===label&&p.x>=x&&p.x<=x+w&&p.y>=y&&p.y<=y+h);
   const subtitle=window.__paint.find(p=>p.text===role&&p.x>=x&&p.x<=x+w&&p.y>=y&&p.y<=y+h);
   check(title&&subtitle,id+' name and subtitle actually painted');
   check(subtitle.top>title.bottom,id+' subtitle below title without overlap');
   check(subtitle.bottom<y+h-3,id+' subtitle inside card');
   const counts=window.__paint.filter(p=>/^(V |L |S |[\\d,]+ specs)/.test(p.text)&&p.x>=x&&p.x<=x+w&&p.y>subtitle.y&&p.y<=y+h);
   check(counts.every(p=>p.top>subtitle.bottom),id+' counts clear subtitle');
   evidence.push({id,label,role,title,subtitle,counts,card:[x,y,w,h]});
  }
  result.dataset.evidence=JSON.stringify(evidence);result.textContent='PASS';
 }catch(error){result.textContent='FAIL: '+error.message;}
 document.body.append(result);
},1400);
</script>"""
    page.write_text(
        _build_page(monkeypatch, tmp_path, _SEARCH_ROWS)
        .replace("<script>", spy + "<script>", 1)
        .replace("</body>", probe + "</body>")
    )
    destination = Path(os.environ.get("ARCHITECTURE_EVIDENCE_DIR", str(tmp_path))).resolve()
    destination.mkdir(exist_ok=True, parents=True)
    out = subprocess.run(
        [
            _chrome(),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--window-size=1440,1000",
            "--virtual-time-budget=5000",
            f"--screenshot={destination / 'candidate-model-fixture-root.png'}",
            "--dump-dom",
            page.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout
    _assert_browser_document(out)
    match = re.search(r'<output[^>]*id="subtitle-result"[^>]*>.*?</output>', out)
    (destination / "candidate-model-fixture-subtitles.txt").write_text(
        "Candidate model with test rows, NOT the real live-payload preview.\n"
        + (match[0] if match else out[-2000:])
        + "\n"
    )
    assert match and ">PASS</output>" in match[0], out[-3000:]


@pytest.mark.spec("PIPE-PAGES-R042")
def test_primary_part_display_labels_use_reviewed_title_case() -> None:
    tree = Tree(json.loads((PKG / "model.json").read_text()))
    expected = {
        "webui.api": "Arbora API Consumer",
        "webui.apps": "Application Surface",
        "webui.design": "Browser Design System",
        "webui.decide": "Decision Evidence",
        "webui.fin": "Markets App",
        "webui.id": "Identity Screens",
        "tui.quality": "Source Quality and Repo Standards",
        "tui.client": "Operation Client",
        "tui.chat": "Chat Transport",
        "tui.coding": "Coding Session",
        "tui.tasks": "Tasks and Runs",
        "tui.screens": "Terminal Views",
        "geniusbot.backend": "Backend Integration",
        "geniusbot.lifecycle": "Desktop Lifecycle",
        "geniusbot.approvals": "Governed Approvals",
        "geniusbot.terminal": "Embedded Terminal",
        "geniusbot.panels": "Operator Panels",
        "geniusbot.tokens": "Design Tokens",
        "geniusbot.docs": "Documentation and Guardrails",
        "geniusbot.runs": "Run Inspection",
        "geniusbot.quality": "Source Quality",
        "ar.door": "Door: Identity and Admission",
        "ar.ops": "Served Operations API",
        "ar.mcp": "MCP Server and Multiplexer",
        "ar.a2a": "A2A Serving",
        "ar.acp": "ACP Gateway",
        "ar.fleet": "Fleet Catalog and Tools",
        "ar.host": "Host Composition",
        "ar.control": "Control Plane",
        "ar.gateway": "Gateway and Widgets",
        "ar.ingest": "Connector Ingest",
        "ar.finance": "Finance and Market Projections",
        "ar.deploy": "Deployment and Release",
        "au.loop": "Run Loop and Harness",
        "au.graph": "Graph Executor",
        "au.runtime": "Workspace Runtime",
        "au.rlm": "Recursive Model Runner",
        "au.scm": "Changeset Development Loop",
        "au.boundary": "Boundary Deconstruction",
        "sdk.control": "Connector Control",
        "sdk.ingest": "Source Ingest",
        "sdk.wb": "Governed Write-Back",
        "sdk.repo": "Repository Transport",
        "sdk.scm": "Source Client and Workspace",
        "sdk.fin": "Finance Sources",
        "sdk.feeds": "Observability Feeds",
        "sdk.release": "Quality and Release",
        "eg.decide": "Decision Engine",
        "eg.evo": "Self-Evolution",
        "eg.ingest": "Ingest and Repository Index",
        "eg.scm": "Source Authority and Changesets",
        "eg.query": "Query and Reasoning",
        "eg.compute": "Graph Compute",
        "eg.packs": "Ontology and Packs",
        "eg.durable": "Durable Kernel",
        "eg.storage": "Storage Layers",
        "eg.udp": "Unified Data Plane",
        "eg.identity": "Identity and Scope",
        "eg.place": "Placement and Workers",
        "eg.fin": "Finance Primitives",
        "eg.contract": "Client and Contract",
        "egserver.bin": "Executable and Subcommands",
        "egserver.dispatch": "Request Dispatch",
        "egserver.wire": "Wire Protocol Adapters",
        "egserver.obs": "Telemetry and Audit",
        "egserver.image": "Container Image",
    }
    for node_id, label in expected.items():
        assert tree.nodes[node_id]["label"] == label
