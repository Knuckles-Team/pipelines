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
from scripts.architecture_explorer.place import Placer, Tree, _group_key, unmapped_violations, validate_code  # noqa: E402
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
    assert where["CORE-R010"] == "core"
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
    assert where["SIDE-R002"] == "side"
    assert unmapped_violations(tree, direct, []) == []


@pytest.mark.spec("PIPE-PAGES-R042")
def test_a_row_on_a_container_descends_to_a_leaf_or_stays_on_the_family_node() -> None:
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
    assert unmapped_violations(tree, direct, []) == []


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
def test_vocabulary_additions_mapping_accepts_canonical_reuse_rollup() -> None:
    assert _group_key("cqconn", "infrastructure-v1.ttl additions rollup") == "Vocabulary additions"
    assert _group_key("cqconn", "sdlc_lifecycle-v1.ttl additions plus software-v1 canonical reuse rollup") == (
        "Vocabulary additions"
    )
    assert _group_key("cqconn", "lifecycle contract rollup") is None


@pytest.mark.spec("PIPE-PAGES-R042")
def test_build_fails_on_a_family_with_no_node(monkeypatch) -> None:
    rows = [_row("EG-SCM-R999", "Nothing names this row", family="family-no-part-owns", repo="medulla")]

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
    assert "<title>Canopy — Knuckles-Team ecosystem architecture</title>" in bare[:8192]
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
    # Medulla's checkout directory followed the repository rename; the other
    # repositories still keep their legacy directory name.
    local_dir = {"medulla": "medulla"}
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
        assert entry["local"] == f"agent-packages/{local_dir.get(slug, old_slug)}"
        assert registry["pages_node"][slug] == node_id
        assert tree.nodes[node_id]["repo"] == slug
        if slug == "axil":
            family, source = "desktop-client", "geniusbot/backend.py"
            row = _row("AXIL-CLIENT-R001", "Backend integration", family, slug)
        elif slug == "meristem":
            family, source = "harness-cycle", "agent_utilities/harness/plan.py"
            row = _row("MERISTEM-HARNESS-CYCLE-R001.2", "Propose", family, slug)
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
            "SCION-CONNECTOR-CONTROL-R030",
            "SDK provides GraphQL introspection context helpers for connector tools",
            "SCION-CONNECTOR-CONTROL",
            "scion-sdk",
        ),
        _row(
            "SCION-CONNECTOR-CONTROL-R030.1",
            "SDK owns the one GraphQL client for connectors",
            "SCION-CONNECTOR-CONTROL",
            "scion-sdk",
        ),
        _row(
            "SCION-CONNECTOR-CONTROL-R043",
            "SDK declares a source access contract for the engine client",
            "SCION-CONNECTOR-CONTROL",
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
    html = _build_page(monkeypatch, tmp_path, _SEARCH_ROWS, aliases={"OLDSCION-": "SCION-CONNECTOR-CONTROL-"})
    index = _payload(html)["search"]
    assert index["aliases"] == {"OLDSCION-": "SCION-CONNECTOR-CONTROL-"}
    (hits,) = _node_search(index, ["OLDSCION-R030.1"])
    assert hits[0]["id"] == "SCION-CONNECTOR-CONTROL-R030.1"


@pytest.mark.spec("PIPE-PAGES-R042.2")
@_NEEDS_LAYOUT
def test_a_capability_search_ranks_the_owning_row_first(monkeypatch, tmp_path: Path) -> None:
    index = _payload(_build_page(monkeypatch, tmp_path, _SEARCH_ROWS))["search"]
    (hits,) = _node_search(index, ["GraphQL client"])
    ids = [h["id"] for h in hits]
    assert ids[0] == "SCION-CONNECTOR-CONTROL-R030.1"
    assert {"CONN-ADGUARD-HOME-AGENT-R002", "SCION-CONNECTOR-CONTROL-R030"} <= set(ids[:4])
    assert hits[0]["repo"] == "scion-sdk" and hits[0]["kind"] == "row"


@pytest.mark.spec("PIPE-PAGES-R042.2")
@_NEEDS_LAYOUT
def test_an_id_search_is_exact(monkeypatch, tmp_path: Path) -> None:
    index = _payload(_build_page(monkeypatch, tmp_path, _SEARCH_ROWS))["search"]
    exact, lower, parent, prefix, nothing = _node_search(
        index,
        [
            "SCION-CONNECTOR-CONTROL-R030.1",
            "sdk-connector-control-r030.1",
            "SCION-CONNECTOR-CONTROL-R030",
            "SCION-CONNECTOR-CONTROL-R04",
            "SCION-CONNECTOR-CONTROL-R999",
        ],
    )
    assert [h["id"] for h in exact] == ["SCION-CONNECTOR-CONTROL-R030.1"]
    assert [h["id"] for h in lower] == ["SCION-CONNECTOR-CONTROL-R030.1"]
    assert [h["id"] for h in parent] == ["SCION-CONNECTOR-CONTROL-R030", "SCION-CONNECTOR-CONTROL-R030.1"]
    assert [h["id"] for h in prefix] == ["SCION-CONNECTOR-CONTROL-R043"]
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
    assert re.search(r'<li data-spec="SCION-CONNECTOR-CONTROL-R030.1" class="flash"', out)
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
    assert "const left=gutter+12, right=sx0+sw0-8" in html
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
def test_header_carries_the_agent_strip_and_the_page_has_no_footer(monkeypatch, tmp_path: Path) -> None:
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
    head = html[html.index("<header") : html.index("</header>")]
    strip = head[head.index('id="agent-strip"') :]
    assert f'href="{_GUIDE}"' in strip and f'href="{_FRONT_DOOR}"' in strip and "at least every 30 minutes" in strip
    assert "<h1>Canopy</h1>" in head and strip.rindex("<details") > strip.index("at least every 30 minutes")
    assert "<footer" not in html and 'id="foot"' not in html and 'id="note"' not in html
    assert html.index('id="agent-strip"') < html.index('<main class="work"')
    assert "font:500 11px/1.4" in html
    assert 'id="freshlist"' in html and 'f.append(el("span",{text:r+"@"' not in html
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
def test_contribution_path_is_in_the_header_head_and_llms_txt() -> None:
    head = explorer.DOC_HEAD
    assert f'<link rel="help" href="{_GUIDE}">' in head and f'<link rel="start" href="{_FRONT_DOOR}">' in head
    assert '<meta name="description"' in head and _FRONT_DOOR in head[head.index('<meta name="description"') :]
    html = (explorer.HERE / "template.html").read_text()
    block = html[html.index('<details id="contribute"') : html.index("</details>", html.index('id="contribute"'))]
    assert " open" not in block.split(">", 1)[0]
    assert "<summary>How to contribute</summary>" in block and block.count("<li>") == 5
    assert html.index('id="agent-strip"') < html.index('id="contribute"') < html.index('<main class="work"')
    assert html.index('id="contribute"') < html.index("</header>")
    for url in (explorer.FRONT_DOOR, explorer.CONTRIBUTING, explorer.ARBORA_DEVELOPMENT):
        assert url in block
    assert (explorer.FRONT_DOOR, explorer.CONTRIBUTING) == (_FRONT_DOOR, _GUIDE)
    assert explorer.EXPLORER == explorer.CANONICAL
    shape = details.detail_path("REPO", "FAM").replace("REPO", "<repo>").replace("FAM", "<family>")
    assert explorer.DETAILS_PATTERN == explorer.CANONICAL + shape
    llms = explorer.llms_txt()
    assert _FRONT_DOOR in llms and _GUIDE in llms and explorer.SKILLS in llms and explorer.DETAILS_PATTERN in llms
    assert all(f"{i}. " in llms for i in range(1, 6))


@pytest.mark.spec("PIPE-PAGES-R042.12")
def test_page_title_header_and_llms_txt_name_canopy() -> None:
    html = (explorer.HERE / "template.html").read_text()
    assert "<title>Canopy — Knuckles-Team ecosystem architecture</title>" in html[:200]
    assert "<h1>Canopy</h1>" in html and "Arbora Architecture Explorer" not in html
    head = explorer.DOC_HEAD
    desc = head[head.index('<meta name="description" content="') :].split('">', 1)[0]
    assert "Canopy shows the whole ecosystem, its specs and its delivery state" in desc and _FRONT_DOOR in desc
    assert explorer.llms_txt().startswith("# Canopy")
    assert "Canopy" in explorer.REDIRECT and "Architecture Explorer" not in explorer.REDIRECT
    theme = (Path(__file__).resolve().parents[1] / "templates/mkdocs-theme/overrides/main.html").read_text()
    assert ">Canopy</a>" in theme and "Architecture Explorer" not in theme


def _style_without_opaque_blocks() -> tuple[str, list[str]]:
    import re

    css = (explorer.HERE / "template.html").read_text()
    css = re.sub(r"/\*.*?\*/", "", css[css.index("<style>") : css.index("</style>")], flags=re.S)
    opaque = []
    for marker in ("@media (prefers-reduced-transparency: reduce){", "@media (forced-colors: active){"):
        start = css.index(marker)
        depth = 0
        for i in range(css.index("{", start), len(css)):
            depth += css[i] == "{"
            depth -= css[i] == "}"
            if depth == 0:
                break
        opaque.append(css[start : i + 1])
        css = css[:start] + css[i + 1 :]
    return css, opaque


@pytest.mark.spec("PIPE-PAGES-R049")
def test_every_surface_uses_a_glass_level_and_layers_stay_translucent() -> None:
    import re

    css, opaque = _style_without_opaque_blocks()
    assert all("background:" in block for block in opaque)
    alpha = {}
    for level in ("chrome", "control", "reading"):
        for token in (f"--glass-{level}:", f"--glass-{level}-edge:", f"--glass-{level}-hi:", f"--glass-{level}-blur:"):
            assert css.count(token) >= 3, token  # light root plus both dark blocks
        alpha[level] = float(re.search(rf"--glass-{level}:rgb\([^/)]*/ \.(\d+)\)", css).group(1)) / 100
    rules = [(sel.strip(), body) for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css)]
    listed = {
        "header.top": "chrome",
        ".toolbar": "chrome",
        ".panel": "reading",
        ".map-notes": "reading",
        ".results": "reading",
        ".xbody": "control",
        ".xbody details": "control",
        ".fresh": "control",
        ".hint": "control",
        ".stat div": "control",
        ".step": "control",
        ".zoom .btn": "control",
        ".search input": "control",
        ".chip": "control",
        ".btn": "control",
        ".kids button": "control",
        ".links button": "control",
        ".badge": "control",
        ".goal": "control",
        ".prio": "control",
        ".crumbs button": "control",
        ".legend>span": "control",
    }
    for surface, level in listed.items():
        fills = []
        for sel, body in rules:
            if surface in [p.strip() for p in sel.split(",")]:
                fills += re.findall(r"(?:^|;)\s*background:([^;]+)", body)
        assert fills, f"{surface} has no fill"
        for fill in fills:
            if fill.strip() in ("none", "transparent"):
                continue
            assert not re.search(r"var\(--(surface|sheet|bg)\)|#[0-9a-fA-F]{3,8}\b", fill), f"opaque fill {surface}"
            token = re.search(r"var\(--(glass-\w+)\)", fill)
            assert token, f"{surface} fill is not a glass token: {fill}"
            if token.group(1) not in ("glass-selected", "glass-active"):
                mix = re.search(r"color-mix\(in srgb,\s*var\(--glass-\w+\)\s*(\d+)%", fill)
                own = alpha[token.group(1).removeprefix("glass-")] * (int(mix.group(1)) / 100 if mix else 1)
                assert own <= alpha[level] + 1e-9, f"{surface} alpha exceeds its {level} level"
    selected = re.findall(r"([^{}]*\[aria-pressed=\"true\"\][^{}]*)\{([^{}]*)\}", css)
    assert selected and all(
        "var(--fg)" not in re.findall(r"background:([^;]+)", b)[0] for _, b in selected if "background" in b
    )
    for sel, body in selected:
        assert "var(--glass-selected)" in body or "background" not in body, sel
    for surface in (
        ".panel",
        ".results",
        ".fresh",
        ".hint",
        ".map-notes",
        "header.top",
        ".toolbar",
        ".btn",
        ".chip",
        ".badge",
        ".crumbs button",
        ".legend>span",
        ".search input",
    ):
        assert any("backdrop-filter:blur(var(--glass-" in body for sel, body in rules if surface in sel.split(",")), (
            surface
        )
    assert not any("backdrop-filter" in body for sel, body in rules if "canvas" in sel and "cv" in sel)


@pytest.mark.spec("PIPE-PAGES-R050")
def test_reduced_motion_disables_parallax_scale_and_pulse() -> None:
    html = (explorer.HERE / "template.html").read_text()
    css = html[html.index("<style>") : html.index("</style>")]
    block = css[css.index("@media (prefers-reduced-motion: reduce){") :]
    block = block[: block.index("\n}\n")]
    assert "translate:none" in block and "transform:none" in block
    assert "scale(.97)" in css and "cubic-bezier(.34,1.56,.64,1)" in css and "transform 160ms" in css
    js = html[html.index("<script>") :]
    assert "const parallaxOn = () => !reduced()" in js
    assert "if(pendingPulse&&!reduced())" in js and "if(!tintFrom||reduced()||t>=1) writeTint(tintTo)" in js
    assert js.index("syncOcean(cam,t)") < js.index(
        "if(t>=1){ anim=null"
    )  # background reads the camera on the same frame
    assert 'dataset.oceanMotion==="running"' in js  # the ocean motion control stops the parallax


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
    assert "egserver" not in nodes
    stem = {node["id"]: node for node in nodes["eg"]["children"]}["egserver"]
    assert stem["label"] == "Medulla Stem"
    assert {child["id"] for child in stem["children"]} >= {"egserver.bin", "egserver.dispatch", "egserver.wire"}
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
        f"AXIL-CLIENT-R{number:03d}{suffix}": f"geniusbot.{part}"
        for part, numbers in _AXIL_PARTS.items()
        for number in numbers
        for suffix in ("", ".1", ".1.1")
    }
    rows = [_row(rid, "Requirement", "desktop-client", "axil") for rid in expected]
    unknown = [_row(rid, "Requirement", "desktop-client", "axil") for rid in ("AXIL-CLIENT-R021", "AXIL-CLIENT-R0010")]
    direct = Placer(tree).run(rows + unknown)
    placed = [(row["id"], nid) for nid, entries in direct.items() for row in entries]
    assert len(placed) == len(rows + unknown)
    assert dict(placed) == {**expected, **{row["id"]: "geniusbot" for row in unknown}}
    assert all(tree.nodes[nid]["repo"] == "axil" for nid in expected.values())


@pytest.mark.spec("PIPE-PAGES-R042")
@_NEEDS_LAYOUT
def test_axil_parts_survive_generation_without_changing_rows_or_statuses(monkeypatch, tmp_path: Path) -> None:
    rows = [
        {**_row(f"AXIL-CLIENT-R{number:03d}", "Requirement", "desktop-client", "axil"), "status": status}
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
    """Validate motion controls; unforced elapsed-time rendering is captured separately via CDP."""
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
    check(animations.every(a=>a.effect.getTiming().duration<=20000),'bounded visible flow cycles');
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
 const m=this.measureText(text);window.__paint.push({text,x,y,font:this.font,left:x-m.actualBoundingBoxLeft,right:x+m.actualBoundingBoxRight,top:y-m.actualBoundingBoxAscent,bottom:y+m.actualBoundingBoxDescent});
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
  const band=window.__paint.find(p=>p.text==='Engine Core, Connectors and Sources');
  check(band,'complete engine band heading actually painted');
  for(const id of ['eg','pipelines']){
   const r=a.rect(id), x=(r[0]-a.cam.x)*a.cam.k,y=(r[1]-a.cam.y)*a.cam.k,w=r[2]*a.cam.k,h=r[3]*a.cam.k;
   check(band.right+4<=x||band.left-4>=x+w||band.bottom+3<=y||band.top-3>=y+h,'band reading plate does not overlap '+id);
  }
  evidence.push({band});
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


@pytest.mark.spec("PIPE-PAGES-R042")
@_NEEDS_LAYOUT
@pytest.mark.skipif(_chrome() is None, reason="no headless Chromium available")
@pytest.mark.parametrize(
    "node,viewport",
    [("root", "1440,1000"), ("root", "390,844"), ("webui", "1440,1000"), ("webui", "390,844"), ("eg", "1440,1000")],
)
def test_ocean_browser_count_text_and_completion_tracks_never_overlap(
    monkeypatch, tmp_path: Path, node: str, viewport: str
) -> None:
    """Actual fillText/fillRect bounds at default and nested cameras; not an inferred DOM test."""
    import os
    import subprocess

    ids = []

    def visit(n):
        ids.append(n["id"])
        for child in n.get("children", []):
            visit(child)

    visit(json.loads((PKG / "model.json").read_text()))
    spy = """<script>
window.__countPaint=[];window.__barPaint=[];window.__allPaint=[];
const originalText=CanvasRenderingContext2D.prototype.fillText, originalRect=CanvasRenderingContext2D.prototype.fillRect, originalClear=CanvasRenderingContext2D.prototype.clearRect;
CanvasRenderingContext2D.prototype.clearRect=function(...args){
 window.__countPaint=[];window.__barPaint=[];window.__allPaint=[];
 const box=this.canvas.getBoundingClientRect();
 window.__countFrame={cam:{...window.__arch.cam},width:box.width,height:box.height,fonts:document.fonts.status};
 return originalClear.apply(this,args);
};
CanvasRenderingContext2D.prototype.fillText=function(text,x,y,...rest){const m=this.measureText(text);window.__allPaint.push({text,x,y,font:this.font,top:y-m.actualBoundingBoxAscent,bottom:y+m.actualBoundingBoxDescent});if(/^(V |L |S |[\\d,]+ specs)/.test(text))window.__countPaint.push({text,left:x-m.actualBoundingBoxLeft,right:x+m.actualBoundingBoxRight,top:y-m.actualBoundingBoxAscent,bottom:y+m.actualBoundingBoxDescent});return originalText.call(this,text,x,y,...rest);};
CanvasRenderingContext2D.prototype.fillRect=function(x,y,w,h){if(h>=1.5&&h<=4.950001&&w>20)window.__barPaint.push({x,y,w,h});return originalRect.call(this,x,y,w,h);};
</script>"""
    probe = """<script>
setTimeout(async()=>{
 await document.fonts.ready;
 const result=document.createElement('output');result.id='count-track-result';
 const current=()=>{const box=document.getElementById('cv').getBoundingClientRect();return {cam:{...window.__arch.cam},width:box.width,height:box.height,fonts:document.fonts.status};};
 try{
  const faces=await document.fonts.load('500 6px Inter');
  if(!faces.some(face=>face.family.replaceAll('"','').replaceAll("'",'')==='Inter'&&face.status==='loaded'))throw Error('Count probe Inter face not loaded');
  let previous='',stable=0;
  for(let attempt=0;attempt<60;attempt++){
   await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
   const now=JSON.stringify(current()),paint=JSON.stringify(window.__countFrame);
   stable=now===paint&&now===previous&&window.__barPaint.length?stable+1:0;previous=now;
   if(stable>=2)break;
  }
  if(stable<2)throw Error('Count probe did not reach a matching stable painted camera');
  const a=window.__arch,evidence=[],topLevel=new Set(PAYLOAD.tree.children.map(n=>n.id));
  for(const id of IDS){
   const r=a.rect(id);if(!r)continue;
   const x=(r[0]-a.cam.x)*a.cam.k,y=(r[1]-a.cam.y)*a.cam.k,w=r[2]*a.cam.k,h=r[3]*a.cam.k;
   const bar=window.__barPaint.find(b=>Math.abs(b.x-(x+w*.06))<.05&&Math.abs(b.w-w*.88)<.05&&b.y>y+h*.5&&b.y<y+h);
   if(!bar)continue;
   const counts=window.__countPaint.filter(p=>p.left>=x-.1&&p.right<=x+w+.1&&p.top>y+h*.5&&p.bottom<=y+h);
   if(!counts.length)continue;
   for(const p of counts)if(p.bottom>bar.y-2)throw Error(id+' count/bar overlap: '+JSON.stringify({p,bar}));
   const baseHeight=Math.max(1.5,Math.min(3,h*.02)),expectedHeight=baseHeight*(topLevel.has(id)?1.65:1);
   const originalBottom=y+h-Math.max(3,Math.min(5,h*.04))+baseHeight;
   if(Math.abs(bar.h-expectedHeight)>.001)throw Error(id+' wrong top-level/nested bar height');
   if(Math.abs(bar.y+bar.h-originalBottom)>.001)throw Error(id+' progress bottom edge moved');
   evidence.push({id,bar,counts,topLevel:topLevel.has(id),baseHeight,expectedHeight,originalBottom});
  }
  if(a.selected==='root'&&window.innerWidth>1000){
   const headings=['People and Clients','Front Ends','Arbora Door','Agent Control Plane and Skills','Engine Core, Connectors and Sources'].map(text=>window.__allPaint.find(p=>p.text===text));
   if(headings.some(p=>!p)||new Set(headings.map(p=>p.font)).size!==1)throw Error('Overview headings must share one complete-label font size');
   for(const [id,role] of [['sdk','Connector SDK'],['au','Agent Harness'],['skills','Agent Skills'],['webui','Browser Experience'],['tui','TUI / CLI'],['geniusbot','Desktop GUI']]){
    const r=a.rect(id),x=(r[0]-a.cam.x)*a.cam.k,y=(r[1]-a.cam.y)*a.cam.k,w=r[2]*a.cam.k,h=r[3]*a.cam.k;
    if(!window.__allPaint.some(p=>p.text===role&&p.x>=x&&p.x<=x+w&&p.top>=y&&p.bottom<=y+h))throw Error(id+' public overview subtitle missing');
    if(!evidence.some(e=>e.id===id))throw Error(id+' public overview count track missing');
   }
  }
  if(evidence.length<2)throw Error('Insufficient actual closed-card paint coverage');
  result.dataset.evidence=JSON.stringify(evidence);result.textContent='PASS';
 }catch(error){result.textContent='FAIL: '+error.message;}
 result.dataset.diagnostics=JSON.stringify({frame:window.__countFrame,current:current(),counts:window.__countPaint,bars:window.__barPaint,allPaint:window.__allPaint});
 document.body.append(result);
},1600);
</script>""".replace("IDS", json.dumps(ids))
    destination = Path(os.environ.get("ARCHITECTURE_EVIDENCE_DIR", str(tmp_path))).resolve()
    destination.mkdir(exist_ok=True, parents=True)
    # Hosted capture already retained the original public payload with this exact renderer.
    # Exercise its real default-card sizes, not only the smaller unit-test data fixture.
    captured_page = destination / "index.html"
    source = (
        _with_document_mode_probe(captured_page.read_text())
        if captured_page.is_file()
        else _build_page(monkeypatch, tmp_path, _SEARCH_ROWS)
    )
    source_kind = (
        "Original captured public payload with candidate renderer"
        if captured_page.is_file()
        else "Candidate model fixture"
    )
    page = tmp_path / "count-track.html"
    page.write_text(source.replace("<script>", spy + "<script>", 1).replace("</body>", probe + "</body>"))
    name = f"count-track-{node}-{viewport.replace(',', 'x')}"

    def capture_count(page_url: str, capture_name: str) -> str:
        result = subprocess.run(
            [
                shutil.which("node"),
                str(ROOT / "tests/architecture_count_capture.cjs"),
                _chrome(),
                page_url,
                viewport,
                str(destination / (capture_name + ".png")),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        (destination / (capture_name + ".stderr.txt")).write_text(result.stderr)
        if result.returncode:
            (destination / (capture_name + ".failed.txt")).write_text(result.stdout[-12000:])
        assert result.returncode == 0, result.stderr[-5000:]
        return result.stdout

    out = capture_count(page.as_uri() + (f"#node={node}" if node != "root" else ""), name)
    _assert_browser_document(out)
    match = re.search(r'<output[^>]*id="count-track-result"[^>]*>.*?</output>', out)
    (destination / (name + ".txt")).write_text(
        source_kind + "; real canvas paint bounds.\n" + (match[0] if match else out[-3000:]) + "\n"
    )
    assert match and ">PASS</output>" in match[0], out[-3000:]
    if node == "root" and viewport == "1440,1000":
        # Counterfactual is narrowly the two deployed pre-fix formulas, not a fabricated screenshot.
        # The same real browser probe must catch the tall Medulla card before accepting the fix.
        baseline = tmp_path / "previous-count-track.html"
        baseline.write_text(
            page.read_text()
            .replace(
                "barY=sy+sh-Math.max(3,Math.min(5,sh*0.04))-(barHeight-baseBarHeight)",
                "barY=sy+sh-Math.max(3,sh*0.06)",
            )
            .replace(
                "countBaseline=barY-Math.max(1,countMetrics.actualBoundingBoxDescent||0)-3", "countBaseline=sy+sh-pad-3"
            )
            .replace("for(const id of " + json.dumps(ids) + ")", 'for(const id of ["eg"])')
        )
        old = capture_count(baseline.as_uri(), "previous-count-track-root")
        _assert_browser_document(old)
        old_match = re.search(r'<output[^>]*id="count-track-result"[^>]*>.*?</output>', old)
        (destination / "previous-count-track-root.txt").write_text(
            source_kind
            + " with ONLY the deployed previous bar/count formulas restored. Expected regression failure, not a full previous-theme rendering.\n"
            + (old_match[0] if old_match else old[-3000:])
            + "\n"
        )
        assert old_match and "FAIL: eg count/bar overlap" in old_match[0], old[-3000:]


@pytest.mark.spec("PIPE-PAGES-R042")
@_NEEDS_LAYOUT
@pytest.mark.skipif(_chrome() is None, reason="no headless Chromium available")
@pytest.mark.parametrize(
    "camera,viewport",
    [
        (camera, viewport)
        for camera in ("default", "root", "webui", "eg", "connectors")
        for viewport in ("1440,1000", "390,844")
    ],
)
def test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels(
    monkeypatch, tmp_path: Path, camera: str, viewport: str
) -> None:
    """Independent actual glyph bounds and segment intersection checks, including native-zoom deferral."""
    import gzip
    import hashlib
    import os
    import subprocess

    from scripts.architecture_explorer.visual_preview import compact_diagnostic_dom, extract_payload

    destination = Path(os.environ.get("ARCHITECTURE_EVIDENCE_DIR", str(tmp_path))).resolve()
    destination.mkdir(exist_ok=True, parents=True)
    captured_page = destination / "index.html"
    source = (
        _with_document_mode_probe(captured_page.read_text())
        if captured_page.is_file()
        else _build_page(monkeypatch, tmp_path, _SEARCH_ROWS)
    )
    theme = "dark" if viewport == "390,844" else "light"
    source = source.replace('<html lang="en">', f'<html lang="en" data-theme="{theme}">')
    raw, _ = extract_payload(source)
    source_kind = "Original captured public payload" if captured_page.is_file() else "Candidate model fixture"
    spy = """<script>
window.__annotationPaint=[];
const textPaint=CanvasRenderingContext2D.prototype.fillText,clearPaint=CanvasRenderingContext2D.prototype.clearRect;
CanvasRenderingContext2D.prototype.clearRect=function(...args){window.__annotationPaint=[];return clearPaint.apply(this,args);};
CanvasRenderingContext2D.prototype.fillText=function(text,x,y,...rest){
 const m=this.measureText(text);
 window.__annotationPaint.push({text:String(text),x,y,font:this.font,alpha:this.globalAlpha,
  rect:[x-m.actualBoundingBoxLeft,y-m.actualBoundingBoxAscent,m.actualBoundingBoxLeft+m.actualBoundingBoxRight,m.actualBoundingBoxAscent+m.actualBoundingBoxDescent]});
 return textPaint.call(this,text,x,y,...rest);
};
</script>"""
    probe = (
        """<script>
setTimeout(async()=>{
 await document.fonts.ready;
 const result=document.createElement('output');result.id='annotation-result';result.hidden=true;
 try{
  const faces=await document.fonts.load('500 11px Inter');
  if(!faces.some(face=>face.family.replaceAll('"','').replaceAll("'",'')==='Inter'&&face.status==='loaded'))throw Error('Actual Inter face not loaded');
  if(document.documentElement.dataset.theme!==THEME)throw Error('Wrong capture theme');
  if(window.__arch.selected!==(CAMERA==='default'?'root':CAMERA))throw Error('Wrong actual camera target');
  const evidence=window.__arch.annotations(),canvas=document.getElementById('cv').getBoundingClientRect();
  const overlap=(a,b)=>a[0]<b[0]+b[2]&&b[0]<a[0]+a[2]&&a[1]<b[1]+b[3]&&b[1]<a[1]+a[3];
  const inside=(p,r)=>p[0]>=r[0]&&p[0]<=r[0]+r[2]&&p[1]>=r[1]&&p[1]<=r[1]+r[3];
  const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  const on=(a,b,c)=>Math.abs(cross(a,b,c))<1e-7&&c[0]>=Math.min(a[0],b[0])-1e-7&&c[0]<=Math.max(a[0],b[0])+1e-7&&c[1]>=Math.min(a[1],b[1])-1e-7&&c[1]<=Math.max(a[1],b[1])+1e-7;
  const meets=(a,b,c,d)=>{
   const p=cross(a,b,c),q=cross(a,b,d),r=cross(c,d,a),s=cross(c,d,b);
   return (p*q<0&&r*s<0)||on(a,b,c)||on(a,b,d)||on(c,d,a)||on(c,d,b);
  };
  const segmentRect=(a,b,r)=>{
   if(inside(a,r)||inside(b,r))return true;
   const corners=[[r[0],r[1]],[r[0]+r[2],r[1]],[r[0]+r[2],r[1]+r[3]],[r[0],r[1]+r[3]]];
   return corners.some((p,i)=>meets(a,b,p,corners[(i+1)%4]));
  };
  if(!evidence.labels.length)throw Error('No annotation coverage');
  if(document.querySelector('#annotations,#annotation-list,#annotation-jump,dialog,[role=dialog]'))throw Error('Unexpected annotation rail/link/popup');
  const painted=[];
  for(const label of evidence.labels){
   if(!label.fullText||label.text.length>36||label.text.includes('…'))throw Error('Missing original or non-authored short caption');
   if(label.placement==='deferred'){
    if(!['scale','space'].includes(label.reason))throw Error('Unexplained native-zoom deferral');
    if(!evidence.labels.some(other=>other.text===label.text&&other.placement==='canvas')&&window.__annotationPaint.some(p=>p.text===label.text&&p.font.startsWith('500 ')&&Math.abs(parseFloat(p.font.slice(4))-label.fs)<.01))throw Error('Deferred caption still painted: '+label.text);
    continue;
   }
   if(label.placement!=='canvas')throw Error('Unknown annotation placement');
   const glyph=window.__annotationPaint.find(p=>p.text===label.text&&Math.abs(p.x-(label.rect[0]+(label.marker?12:0)))<.01&&Math.abs(p.y-label.rect[1])<.01);
   if(!glyph)throw Error('Caption not actually painted: '+label.text);
   if(!glyph.font.includes('Inter'))throw Error('Inconsistent caption typography');
   const r=[glyph.rect[0]-3,glyph.rect[1]-3,glyph.rect[2]+6,glyph.rect[3]+6];
   if(r[0]<0||r[1]<0||r[0]+r[2]>canvas.width||r[1]+r[3]>canvas.height)throw Error('Caption clipped: '+label.text);
   if(evidence.rects.some(b=>overlap(r,b)))throw Error('Caption/card or chrome overlap: '+label.text);
   if(evidence.segments.some(([a,b])=>segmentRect(a,b,r)))throw Error('Caption/connector overlap: '+label.text);
   if(painted.some(p=>overlap(r,p.rect)))throw Error('Caption/caption overlap: '+label.text);
   painted.push({text:label.text,rect:r,font:glyph.font});
  }
  if(['default','root'].includes(CAMERA)){
   for(const text of ['External systems and connectors','Self-evolution loop: evaluate, promote, roll back']){
    if(!evidence.labels.some(label=>label.fullText===text))throw Error('Missing reported regression caption: '+text);
   }
  }
  if(['default','root'].includes(CAMERA)){
   for(const text of ['External Integrations','Self-Evolution'])if(!evidence.labels.some(label=>label.text===text))throw Error('Missing authored short caption: '+text);
  }
  const description=document.querySelector('#panel .desc')?.textContent||'';
  const originalGroups={default:['External systems and connectors','Self-evolution loop: evaluate, promote, roll back'],root:['External systems and connectors','Self-evolution loop: evaluate, promote, roll back'],eg:['Self-evolution loop: evaluate, promote, roll back'],connectors:['External systems and connectors']};
  for(const original of originalGroups[CAMERA]||[])if(!description.includes(original))throw Error('Original group meaning missing from existing Description: '+original);
  result.dataset.evidence=JSON.stringify({source:SOURCE,camera:CAMERA,labels:evidence.labels,painted,obstacleRects:evidence.rects.length,connectorSegments:evidence.segments.length,deferred:evidence.labels.filter(label=>label.placement==='deferred').length});
  result.textContent='PASS';
 }catch(error){result.textContent='FAIL: '+error.message;}
 document.body.append(result);
},1800);
</script>""".replace("CAMERA", json.dumps(camera))
        .replace("SOURCE", json.dumps(source_kind))
        .replace("THEME", json.dumps(theme))
    )
    page = tmp_path / "annotations.html"
    page.write_text(source.replace("<script>", spy + "<script>", 1).replace("</body>", probe + "</body>"))
    name = f"annotations-{camera}-{viewport.replace(',', 'x')}"
    url = page.as_uri() + (f"#node={camera}" if camera != "default" else "")

    def capture_annotation(page_url: str, capture_name: str) -> str:
        result = subprocess.run(
            [
                _chrome(),
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                f"--window-size={viewport}",
                "--virtual-time-budget=5000",
                f"--screenshot={destination / (capture_name + '.png')}",
                "--dump-dom",
                page_url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        out = result.stdout
        _assert_browser_document(out)
        compact, manifest = compact_diagnostic_dom(out, hashlib.sha256(raw.encode()).hexdigest())
        with gzip.open(destination / (capture_name + ".html.gz"), "wt", encoding="utf-8") as compressed:
            compressed.write(compact)
        (destination / (capture_name + ".manifest.json")).write_text(json.dumps(manifest, indent=2))
        (destination / (capture_name + ".stderr.txt")).write_text(result.stderr)
        match = re.search(r'<output[^>]*id="annotation-result"[^>]*>.*?</output>', out)
        (destination / (capture_name + ".txt")).write_text(
            source_kind
            + "; actual glyph paint bounds and independent segment intersections.\n"
            + (match[0] if match else out[-3000:])
            + "\n"
        )
        assert match and ">PASS</output>" in match[0], out[-3000:]
        return out

    capture_annotation(url, name)
    # Native zoom appearance and existing fullscreen controls use real CDP input
    # after the separate unforced-motion sequence in motion_capture.cjs.


@pytest.mark.spec("PIPE-PAGES-R042")
def test_count_capture_uses_real_frame_scheduling_and_handles_browser_exit(tmp_path: Path) -> None:
    import os
    import subprocess

    helper = ROOT / "tests/architecture_count_capture.cjs"
    source = helper.read_text()
    assert "--remote-debugging-pipe" in source and "--virtual-time-budget" not in source
    assert "Target.activateTarget" in source and "Page.bringToFront" in source
    assert "mode==='exact-viewport'" in source and "Emulation.setDeviceMetricsOverride" in source
    assert "state.viewport[0]!==width||state.viewport[1]!==height" in source
    assert "document.getElementById('count-track-result')" in source
    assert source.index("await exited;") < source.index("rmSync(profile,")
    # The repair must retain the page's stable actual-paint synchronization and all
    # count assertions, rather than replacing requestAnimationFrame with a timer.
    tests = (
        Path(__file__)
        .read_text()
        .split("def test_ocean_browser_count_text_and_completion_tracks_never_overlap", 1)[1]
        .split("\n\n@pytest.mark.spec", 1)[0]
    )
    assert "requestAnimationFrame(()=>requestAnimationFrame(resolve))" in tests
    assert "now===paint&&now===previous&&window.__barPaint.length" in tests
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    browser = tmp_path / "exits-immediately"
    browser.write_text("#!/bin/sh\nexit 1\n")
    browser.chmod(0o755)
    result = subprocess.run(
        [node, str(helper), str(browser), "about:blank", "1440,1000", str(tmp_path / "capture.png")],
        env={**os.environ, "TMPDIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert not list(tmp_path.glob("architecture-count-*"))


@pytest.mark.spec("PIPE-PAGES-R042")
@_NEEDS_LAYOUT
@pytest.mark.skipif(_chrome() is None, reason="no headless Chromium available")
@pytest.mark.parametrize(
    "viewport,theme",
    [
        (viewport, theme)
        for viewport in ("1440,1000", "1920,1080", "2560,1440", "390,844")
        for theme in ("light", "dark")
    ],
)
def test_ocean_browser_progress_summary_full_labels_counts_and_swatches_fit(
    monkeypatch, tmp_path: Path, viewport: str, theme: str
) -> None:
    """Real DOM/range bounds at the visible summary, using the existing wall-clock capture helper."""
    import os
    import subprocess

    destination = Path(os.environ.get("ARCHITECTURE_EVIDENCE_DIR", str(tmp_path))).resolve()
    destination.mkdir(exist_ok=True, parents=True)
    captured_page = destination / "index.html"
    source = (
        _with_document_mode_probe(captured_page.read_text())
        if captured_page.is_file()
        else _build_page(monkeypatch, tmp_path, _SEARCH_ROWS)
    )
    source = source.replace('<html lang="en">', f'<html lang="en" data-theme="{theme}">')
    source_kind = "Original captured public payload" if captured_page.is_file() else "Candidate model fixture"
    # Keep the existing helper's terminal sentinel ID, not a second browser dependency.
    # The output explicitly identifies this independent summary probe and its metrics.
    probe = (
        """<script>
setTimeout(async()=>{
 await document.fonts.ready;
 const result=document.createElement('output');result.id='count-track-result';result.hidden=true;
 try{
  if(innerWidth!==REQUESTED_WIDTH||innerHeight!==REQUESTED_HEIGHT)throw Error('Requested summary viewport differs from actual '+innerWidth+'x'+innerHeight);
  if(document.documentElement.dataset.theme!==THEME)throw Error('Wrong summary theme');
  const faces=await document.fonts.load('500 12px Inter');
  if(!faces.some(face=>face.family.replaceAll('"','').replaceAll("'",'')==='Inter'&&face.status==='loaded'))throw Error('Summary Inter face not loaded');
  const stat=document.querySelector('#panel .stat');if(!stat)throw Error('Missing existing sidebar summary');
  stat.scrollIntoView({block:'center',inline:'nearest'});
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const box=r=>({left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height});
  const contains=(a,b)=>b.left>=a.left-.5&&b.top>=a.top-.5&&b.right<=a.right+.5&&b.bottom<=a.bottom+.5;
  const overlaps=(a,b)=>a.left<b.right&&b.left<a.right&&a.top<b.bottom&&b.top<a.bottom;
  const ink=e=>{const r=document.createRange();r.selectNodeContents(e);return r.getBoundingClientRect();};
  const root=PAYLOAD.tree.count,expected=[['Specs','total'],['Verified','VERIFIED'],['Landed','LANDED'],['Specified','SPECIFIED'],['Retired','RETIRED']];
  const rows=[...stat.children],evidence=[],colors=[];
  if(rows.length!==5)throw Error('Summary must show all five full labels');
  for(let i=0;i<expected.length;i++){
   const [label,key]=expected[i],row=rows[i],name=row.querySelector('.status-label span'),value=row.querySelector('b');
   if(!name||name.textContent!==label)throw Error('Missing full status label '+label);
   if(!value||Number(value.textContent.replaceAll(',',''))!==(root[key]||0))throw Error('Incorrect summary count '+label);
   const bounds=row.getBoundingClientRect(),text=ink(name),number=ink(value),summary=stat.getBoundingClientRect();
   if(!contains(summary,bounds)||!contains(bounds,text)||!contains(bounds,number)||overlaps(text,number))throw Error('Clipped/overlapping summary text '+label);
   if(bounds.left<0||bounds.right>innerWidth||bounds.top<0||bounds.bottom>innerHeight)throw Error('Summary row not fully visible '+label);
   for(const previous of evidence)if(overlaps(bounds,previous.bounds))throw Error('Summary cells overlap');
   let swatch=null;
   if(key!=='total'){
    const marker=row.querySelector('.status-swatch');if(!marker||marker.getAttribute('aria-hidden')!=='true')throw Error('Missing decorative status swatch '+label);
    const r=marker.getBoundingClientRect();if(r.width<6||r.height<6||!contains(bounds,r)||overlaps(r,text))throw Error('Clipped/overlapping status swatch '+label);
    const color=getComputedStyle(marker).backgroundColor;
    const reference=document.createElement('i');reference.style.backgroundColor=getComputedStyle(document.documentElement).getPropertyValue('--p-'+key.toLowerCase());document.body.append(reference);
    const expectedColor=getComputedStyle(reference).backgroundColor;reference.remove();
    if(color!==expectedColor||color==='rgba(0, 0, 0, 0)')throw Error('Swatch is not bound to progress color '+label);
    colors.push(color);swatch={bounds:box(r),color};
   }
   evidence.push({label,count:value.textContent,bounds:box(bounds),labelInk:box(text),countInk:box(number),swatch});
  }
  if(new Set(colors).size!==4)throw Error('Progress statuses need distinguishable color swatches');
  if(document.documentElement.scrollWidth>innerWidth)throw Error('Horizontal overflow');
  result.dataset.evidence=JSON.stringify({kind:'Full-name progress summary DOM and glyph bounds',theme:THEME,source:SOURCE,viewport:[innerWidth,innerHeight],rows:evidence});result.textContent='PASS';
 }catch(error){result.textContent='FAIL: '+error.message;}
 document.body.append(result);
},1000);
</script>""".replace("THEME", json.dumps(theme))
        .replace("SOURCE", json.dumps(source_kind))
        .replace("REQUESTED_WIDTH", viewport.split(",")[0])
        .replace("REQUESTED_HEIGHT", viewport.split(",")[1])
    )
    page = tmp_path / "progress-summary.html"
    page.write_text(source.replace("</body>", probe + "</body>"))
    name = f"progress-summary-{viewport.replace(',', 'x')}-{theme}"
    result = subprocess.run(
        [
            shutil.which("node"),
            str(ROOT / "tests/architecture_count_capture.cjs"),
            _chrome(),
            page.as_uri(),
            viewport,
            str(destination / (name + ".png")),
            "exact-viewport",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    (destination / (name + ".stderr.txt")).write_text(result.stderr)
    assert result.returncode == 0, result.stderr[-5000:]
    _assert_browser_document(result.stdout)
    match = re.search(r'<output[^>]*id="count-track-result"[^>]*>.*?</output>', result.stdout)
    (destination / (name + ".txt")).write_text(
        source_kind
        + "; actual progress summary text and swatch bounds.\n"
        + (match[0] if match else result.stdout[-3000:])
        + "\n"
    )
    assert match and ">PASS</output>" in match[0], result.stdout[-3000:]


@pytest.mark.spec("PIPE-PAGES-R042")
def test_rows_matching_no_child_stay_on_the_family_node_and_never_fail_the_build(monkeypatch) -> None:
    """New rows of an owned family whose keywords match no child map to the family's own node."""
    tree = Tree(_model_with_external())
    rows = [_row(f"CORE-R{n}", "Matches no keyword anywhere") for n in range(100, 130)]
    direct = Placer(tree).run(rows)
    assert {nid for nid in direct} == {"core"}
    assert not [n for n in tree.nodes if n.endswith(".unmapped")]
    assert unmapped_violations(tree, direct, []) == []

    shipped = Tree(json.loads((PKG / "model.json").read_text()))
    new = [_row("MEDULLA-DECISION-ENGINE-R9999", "Matches no keyword zzqx", "decision-engine", "medulla")]
    placed = Placer(shipped).run(new)
    assert [nid for nid in placed] == ["eg.decide"]
    assert unmapped_violations(shipped, placed, []) == []


@pytest.mark.spec("PIPE-PAGES-R045")
def test_release_view_lists_scope_progress_and_row_badges(tmp_path: Path) -> None:
    from scripts.architecture_explorer import releases

    def row(rid: str, status: str, repo: str = "medulla") -> dict:
        return {**_row(rid, rid, repo=repo), "status": status, "spec_id": rid.rsplit("-R", 1)[0]}

    rows = [
        row("M-A-R001", "VERIFIED"),
        row("M-A-R002", "SPECIFIED"),
        row("S-B-R001", "VERIFIED", "scion-sdk"),
        row("O-C-R001", "LANDED"),
    ]
    (tmp_path / "P1.yml").write_text(
        json.dumps(
            {
                "id": "P1",
                "name": "Loop",
                "phase": "P1",
                "scenario": "ARBORA-ACCEPTANCE-R006.1",
                "scope": [
                    {"repo": "medulla", "spec": "M-A", "roots": ["M-A-R001", "M-A-R002"]},
                    {"repo": "scion-sdk", "spec": "S-B", "roots": ["S-B-R001"]},
                ],
            }
        )
    )
    manifests = releases.load_manifests(tmp_path)
    view = releases.release_view(manifests, rows)
    (p1,) = view["releases"]
    assert (p1["phase"], p1["scenario_state"], p1["rows"], p1["verified"], p1["share"]) == ("P1", "not run", 3, 2, 67)
    assert [(r["repo"], r["rows"], r["verified"]) for r in p1["repos"]] == [("medulla", 2, 1), ("scion-sdk", 1, 1)]
    assert view["unscheduled"] == 1
    (tmp_path / releases.RUNS_FILE).write_text(json.dumps({"P1": {"state": "passed"}}))
    assert (
        releases.release_view(manifests, rows, releases.load_runs(tmp_path))["releases"][0]["scenario_state"]
        == "passed"
    )
    owner = releases.row_releases(manifests, rows)
    delivery = {"scores": {}, "frontier_set": set(), "unserved_set": set(), "release_of": owner}
    assert explorer.spec_entry(rows[0], delivery)["release"] == "P1"
    assert explorer.spec_entry(rows[3], delivery)["release"] == releases.UNSCHEDULED
    (tmp_path / "P5.yml").write_text(
        json.dumps({"id": "P5", "name": "Rest", "phase": "P5", "scenario": "none", "scope": "all-remaining"})
    )
    rest = releases.release_view(releases.load_manifests(tmp_path), rows)
    assert rest["releases"][1]["rows"] == 1 and rest["unscheduled"] == 0
    template = (PKG / "template.html").read_text()
    assert 'id="vrel"' in template and "Filter the map to" in template and "s.release===relF" in template


def _wcag_ratio(fg: tuple, bg: tuple) -> float:
    def lum(c: tuple) -> float:
        lin = [v / 255 / 12.92 if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.spec("PIPE-PAGES-R049")
def test_glass_text_contrast_is_at_least_4_5_over_the_ocean_in_both_themes() -> None:
    import re

    html = (explorer.HERE / "template.html").read_text()
    css = html[html.index("<style>") : html.index("</style>")]
    blocks = {
        "light": css[css.index(":root{") : css.index("@media (prefers-color-scheme: dark)")],
        "dark": css[css.index(':root[data-theme="dark"]{') : css.index("*{box-sizing")],
    }

    def tokens(block: str) -> dict:
        return dict(re.findall(r"(--[\w-]+):\s*([^;}]+)", block))

    def color(value: str) -> tuple:
        value = value.strip()
        if value.startswith("#"):
            return (*(int(value[i : i + 2], 16) for i in (1, 3, 5)), 1.0)
        nums = re.findall(r"[\d.]+", value)
        return (float(nums[0]), float(nums[1]), float(nums[2]), float(nums[3]) if len(nums) > 3 else 1.0)

    def over(top: tuple, below: tuple) -> tuple:
        a = top[3]
        return (*(top[i] * a + below[i] * (1 - a) for i in range(3)), 1.0)

    for theme, block in blocks.items():
        tok = tokens(block)
        for ocean in ("--ocean-top", "--ocean-bottom"):
            sea = color(tok[ocean])
            for level in ("chrome", "control", "reading"):
                glass = over(color(tok[f"--glass-{level}"]), sea)
                for text in ("--fg", "--muted"):
                    ratio = _wcag_ratio(color(tok[text])[:3], glass[:3])
                    assert ratio >= 4.5, f"{theme} {text} on {level} over {ocean}: {ratio:.2f}"
            # pressed and selected controls: tint on control glass on reading glass on the ocean
            base = over(color(tok["--glass-reading"]), sea)
            for state in ("--glass-selected", "--glass-active"):
                pressed = over(color(tok[state]), over(color(tok["--glass-control"]), base))
                ratio = _wcag_ratio(color(tok["--fg"])[:3], pressed[:3])
                assert ratio >= 4.5, f"{theme} pressed {state} over {ocean}: {ratio:.2f}"


# ------------------------------------------------- spec-driven delivery in Canopy (PIPE-PAGES-R051)

SDD_PLAN = (
    "# Plan: Fam\n\n## Summary\n\nSum.\n\n## Constitution Check\n\n- **I. One owner**: pass, no copy.\n"
    "- **IV. Neutral names**: FAIL - a product name appears.\n\n## Cross-repo seams\n\n"
    "- FAM-R002 hands the result to FAM-R001.\n\n## Delivery phase\n\nRows serve P3.\n\n## Repeat\n\nA.\n\n## Repeat\n\nB.\n"
)
SDD_TASKS = "# Tasks\n\n- [x] Done thing FAM-R001\n- [ ] Open thing Zq-TASK-MARKER\n- [ ] Third thing\n"
SDD_CONSTITUTION = "# Constitution\n\n**Version**: 1.2.0 | **Ratified**: 2026-10-31\n\n## Core Principles\n\n### I. One owner\n\nText.\n"
SDD_DOCS = {
    "spec.md": "# FAM - Fam title\n\n## Purpose\n\nWhy.\n",
    "plan.md": SDD_PLAN,
    "tasks.md": SDD_TASKS,
    "test-spec.md": TEST_MD,
    "research.md": "# Research\n\nNone.\n",
    "checklists/req.md": "# Checklist\n\n- [ ] item\n",
    "contracts/api.yml": "openapi: 3.0.0\n",
}


def _sdd_snapshots() -> list[Snapshot]:
    snaps = _detail_snapshots()
    snap = next(s for s in snaps if s.repo == "pipelines")
    snap.docs = {"fam": dict(SDD_DOCS)}
    snap.files |= {f"specs/fam/{n}" for n in SDD_DOCS}
    snap.constitution = SDD_CONSTITUTION
    return snaps


def _sdd_page(monkeypatch, tmp_path: Path) -> Path:
    return _build_with_details(monkeypatch, tmp_path, _sdd_snapshots())


@pytest.mark.spec("PIPE-PAGES-R051.1")
@_NEEDS_LAYOUT
def test_family_files_carry_every_spec_document_with_an_outline(monkeypatch, tmp_path: Path) -> None:
    page = _sdd_page(monkeypatch, tmp_path)
    doc = json.loads((page.parent / "spec-details/pipelines/fam.json").read_text())
    docs = {d["name"]: d for d in doc["docs"]}
    assert set(docs) == set(SDD_DOCS)
    assert docs["tasks.md"]["label"] == "Tasks" and docs["checklists/req.md"]["label"] == "Checklist: req"
    assert (
        docs["contracts/api.yml"]["label"] == "Contract: api"
        and "<pre><code>openapi" in docs["contracts/api.yml"]["html"]
    )
    outline = {name: [o[2] for o in d["outline"]] for name, d in docs.items()}
    assert outline["plan.md"] == [
        "plan-fam",
        "summary",
        "constitution-check",
        "cross-repo-seams",
        "delivery-phase",
        "repeat",
        "repeat-2",
    ]
    assert details.doc_names({"specs/fam/tasks.md", "specs/fam/contracts/a/b.yml", "specs/fam/notes.md"}, "fam") == [
        "tasks.md"
    ]
    assert "Zq-TASK-MARKER" not in page.read_text()  # documents stay in the lazily loaded family file
    assert "Zq-TASK-MARKER" in (page.parent / "spec-details/pipelines/fam.json").read_text()


@pytest.mark.spec("PIPE-PAGES-R051.2")
@_NEEDS_LAYOUT
def test_a_repository_constitution_is_written_versioned_and_linked(monkeypatch, tmp_path: Path) -> None:
    page = _sdd_page(monkeypatch, tmp_path)
    doc = json.loads((page.parent / "spec-details/pipelines/_constitution.json").read_text())
    assert doc["family"] == "_constitution" and doc["docs"][0]["label"] == "Constitution"
    assert "Core Principles" in doc["docs"][0]["html"]
    assert doc["docs"][0]["url"].endswith("/blob/HEAD/.specify/memory/constitution.md")
    assert _payload(page.read_text())["meta"]["constitutions"] == {"pipelines": "1.2.0"}
    template = (PKG / "template.html").read_text()
    assert "function constitutionSection" in template and '"_constitution/constitution.md"' in template


@pytest.mark.spec("PIPE-PAGES-R051.3")
@_NEEDS_LAYOUT
def test_delivery_cards_carry_title_phase_task_progress_and_document_bits(monkeypatch, tmp_path: Path) -> None:
    from scripts.architecture_explorer import sdd

    page = _sdd_page(monkeypatch, tmp_path)
    card = _payload(page.read_text())["tree"]["cards"]["pipelines"]["fam"]
    assert (card["t"], card["p"], card["k"]) == ("Fam title", "P3", [1, 2])
    expected = sdd.kinds_bits(
        ["spec.md", "plan.md", "tasks.md", "test-spec.md", "research.md", "checklists/req.md", "contracts/api.yml"]
    )
    assert card["d"] == expected and expected & (1 << sdd.KINDS.index("quickstart")) == 0
    # Without a Delivery phase section the phase falls back to the most common release phase of the rows.
    bare = sdd.family_card({"plan.md": "# Plan\n"}, set(), "x", ["P2", "P2", "P4"])
    assert bare["p"] == "P2" and bare["t"] == "Plan" and bare["k"] == [0, 0]
    assert sdd.family_card({}, set(), "x", [])["p"] == ""


@pytest.mark.spec("PIPE-PAGES-R051.3")
@pytest.mark.spec("PIPE-PAGES-R051.4")
def test_the_node_panel_renders_own_cards_and_links_each_document() -> None:
    js = (PKG / "template.html").read_text()
    assert (
        "function deliverySection" in js
        and "const own=famList([n]), below=n.children.length?famList(descNodes(n))" in js
    )
    assert "text:countText(tally(f.rows))" in js and "KINDS.forEach((k,i)=>{ if(!(card.d>>i&1)) return;" in js
    assert 'text:"requirements \u2197"' in js and "const dsec=deliverySection(n)" in js
    # The aggregate table sorts by phase and by progress and counts delivered only for a passed scenario.
    assert '["phase","Sort by phase"],["progress","Sort by progress"]' in js
    assert 'r.status==="VERIFIED"&&PASSED.has(r.release)' in js and 'scenario_state==="passed"' in js
    assert "innerHTML" not in js


@pytest.mark.spec("PIPE-PAGES-R051.5")
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_doc_deep_links_parse_and_round_trip() -> None:
    import subprocess

    script = (
        "const A=require('./search.cjs');"
        "console.log(JSON.stringify(['#node=a.b&doc=fam/plan.md&sec=constitution-check&repo=r','#node=a&doc=fam/checklists/x.md'].map(A.parseHash)));"
        "console.log(A.hashFor('a.b','',{doc:'fam/plan.md',sec:'summary',repo:'r'}),A.hashFor('a','',null));"
    )
    lines = subprocess.run(
        ["node", "-e", script], cwd=PKG, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert json.loads(lines[0]) == [
        {"node": "a.b", "q": "", "doc": "fam/plan.md", "sec": "constitution-check", "repo": "r"},
        {"node": "a", "q": "", "doc": "fam/checklists/x.md"},
    ]
    assert lines[1] == "#node=a.b&doc=fam/plan.md&sec=summary&repo=r #node=a"


@pytest.mark.spec("PIPE-PAGES-R051.5")
def test_outline_anchors_every_plan_heading() -> None:
    markup = details.render_markdown(SDD_PLAN, details.Ctx("pipelines", "fam"))
    names = [o[1] for o in details.outline(markup)]
    assert names == [
        "Plan: Fam",
        "Summary",
        "Constitution Check",
        "Cross-repo seams",
        "Delivery phase",
        "Repeat",
        "Repeat",
    ]
    assert [o[2] for o in details.outline(markup)][-2:] == ["repeat", "repeat-2"]
    template = (PKG / "template.html").read_text()
    assert 'hs[i].id="d-"+o[2]' in template and "function linkRowIds" in template and "ROWNODE[id]" in template
    assert "history.back()" in template and "function openDoc" in template


@pytest.mark.spec("PIPE-PAGES-R051.5")
@pytest.mark.spec("PIPE-PAGES-R051.7")
@_NEEDS_LAYOUT
@pytest.mark.skipif(_chrome() is None, reason="no headless Chromium available")
def test_the_reader_opens_a_plan_section_and_links_row_ids_in_a_browser(monkeypatch, tmp_path: Path) -> None:
    import functools
    import http.server
    import subprocess
    import threading

    page = _sdd_page(monkeypatch, tmp_path)
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
                f"http://127.0.0.1:{server.server_port}/index.html#q=FAM-R001&doc=fam/plan.md&sec=cross-repo-seams&repo=pipelines",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout
    finally:
        server.shutdown()
    reader = out[out.index('<section class="panel reader"') :]
    assert (
        "hidden" not in out[out.index('<section class="panel reader"') : out.index('id="reader"') + 60]
    )  # the reader is open
    assert 'id="d-cross-repo-seams"' in reader and 'class="rowlink"' in reader and ">FAM-R002</a>" in reader
    assert "Constitution: 1 failing" in out  # the card of a plan with a failing principle carries the warning badge


@pytest.mark.spec("PIPE-PAGES-R051.6")
def test_the_program_view_has_a_toggle_and_five_phase_columns() -> None:
    template = (PKG / "template.html").read_text()
    assert template.index('id="vnext"') < template.index('id="vpath"') < template.index('id="vprog"')
    assert ">Delivery</button>" in template and "function renderProgram" in template
    assert '["P1","P2","P3","P4","P5",' in template and "repeat(5,minmax(190px,1fr))" in template
    assert "rel.scenario+" not in template and "ROWSTATE[rel.scenario]" in template and "scenario_state" in template
    for release in sorted((ROOT / "releases").glob("*.yml")):
        manifest = json.loads(release.read_text())
        assert manifest["phase"] in {"P1", "P2", "P3", "P4", "P5"} and manifest["scenario"]


@pytest.mark.spec("PIPE-PAGES-R051.7")
def test_a_failing_principle_in_the_constitution_check_warns() -> None:
    from scripts.architecture_explorer import sdd

    assert sdd.failing_principles(SDD_PLAN) == ["I. One owner: pass, no copy."][:0] + [
        "IV. Neutral names: FAIL - a product name appears."
    ]
    passing = SDD_PLAN.replace("FAIL - a product name appears", "pass")
    assert sdd.failing_principles(passing) == [] and sdd.failing_principles("") == []
    # The template instruction line ("pass or fail") is not a verdict.
    assert sdd.failing_principles("## Constitution Check\n\n- One line per principle: pass or fail, and why.\n") == []
    template = (PKG / "template.html").read_text()
    assert template.count("warnBadge(c.w)") >= 3  # cards, aggregate table and program view


@pytest.mark.spec("PIPE-PAGES-R051.8")
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_search_extras_hold_task_lines_and_plan_headings_and_rank_last(monkeypatch, tmp_path: Path) -> None:
    import subprocess

    from scripts.architecture_explorer import sdd

    snaps = _sdd_snapshots()
    extra = sdd.search_extra(snaps, {("pipelines", "fam"): "core"})
    kinds = [(i[0], i[1]) for i in extra["items"]]
    assert (
        ("x", "Done thing FAM-R001") in kinds
        and ("t", "Open thing Zq-TASK-MARKER") in kinds
        and ("h", "Constitution Check") in kinds
    )
    assert sdd.search_extra(snaps, {}) == {"v": 1, "items": []}  # a family no node owns is not searchable
    index = {
        "v": 1,
        "repos": ["r"],
        "fams": ["f"],
        "st": ["VERIFIED"],
        "nodes": [["n", "Node", "Part.", 0, []]],
        "rows": [["A-R001", "Open thing owner", 0, 0, 0, 0]],
        "aliases": {},
    }
    script = (
        "const A=require('./search.cjs');const ix=JSON.parse(process.argv[1]);const ex=JSON.parse(process.argv[2]);"
        "const h=A.create(ix,null,ex).search('open thing');console.log(JSON.stringify(h.map(x=>[x.kind,x.doc||'',x.node])));"
    )
    out = subprocess.run(
        [
            "node",
            "-e",
            script,
            json.dumps(index),
            json.dumps({"items": [["t", "Open thing Zq", "n", "r", "f", "tasks.md", ""]]}),
        ],
        cwd=PKG,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(out.stdout) == [["row", "", "n"], ["task", "tasks.md", "n"]]
    template = (PKG / "template.html").read_text()
    assert 'fetch("search-extra.json")' in template and "if(h.doc) openDoc(" in template


@pytest.mark.spec("PIPE-PAGES-R051.8")
@_NEEDS_LAYOUT
def test_a_build_writes_search_extras_beside_the_page(monkeypatch, tmp_path: Path) -> None:
    page = _sdd_page(monkeypatch, tmp_path)
    extra = json.loads((page.parent / "search-extra.json").read_text())
    assert any(i[0] == "h" and i[1] == "Delivery phase" and i[6] == "delivery-phase" for i in extra["items"])
    assert all(i[2] for i in extra["items"])  # every item names the node that owns its family


@pytest.mark.spec("PIPE-PAGES-R051.1")
@pytest.mark.spec("PIPE-PAGES-R051.9")
@_NEEDS_LAYOUT
def test_the_page_stays_within_ten_percent_and_inlines_no_document(monkeypatch, tmp_path: Path) -> None:
    page = _sdd_page(monkeypatch, tmp_path)
    html = page.read_text()
    template = (PKG / "template.html").read_text()
    script = template[template.index("// ---------- spec-driven delivery") : template.index("function diagramContext")]
    style = template[template.index("/* Spec-driven delivery") : template.index("/* Full Overstory glass")]
    payload = _payload(html)
    data = len(json.dumps(payload["tree"]["cards"])) + len(json.dumps(payload["meta"]["constitutions"]))
    added = len(script) + len(style) + data
    assert added <= 0.10 * (len(html) - added), f"{added} bytes added to a {len(html)} byte page"
    for marker in ("Zq-TASK-MARKER", "Core Principles", "openapi: 3.0.0"):
        assert marker not in html


@pytest.mark.spec("PIPE-PAGES-R051.9")
def test_new_panels_use_glass_levels_and_respect_reduced_motion() -> None:
    template = (PKG / "template.html").read_text()
    css = template[template.index("<style>") : template.index("</style>")]
    # The program view and the reader are panels, so they take the reading level, its blur and its edge.
    assert 'class="panel program"' in template and 'class="panel reader"' in template
    assert "var(--glass-" in css and "background:var(--surface)" in css
    new_rules = css[css.index("/* Spec-driven delivery") : css.index("/* Full Overstory glass")]
    assert "transition" not in new_rules and "animation" not in new_rules and "backdrop-filter" not in new_rules
    assert not re.search(r"background:\s*(#|rgb\()", new_rules)
    block = css[css.index("@media (prefers-reduced-motion: reduce){") :]
    assert "transition:none!important" in block[: block.index("\n}\n")]
