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
    "agent-connector-sdk": [
        _row(
            "SDK-CONNECTOR-CONTROL-R030",
            "SDK provides GraphQL introspection context helpers for connector tools",
            "SDK-CONNECTOR-CONTROL",
            "agent-connector-sdk",
        ),
        _row(
            "SDK-CONNECTOR-CONTROL-R030.1",
            "SDK owns the one GraphQL client for connectors",
            "SDK-CONNECTOR-CONTROL",
            "agent-connector-sdk",
        ),
        _row(
            "SDK-CONNECTOR-CONTROL-R043",
            "SDK declares a source access contract for the engine client",
            "SDK-CONNECTOR-CONTROL",
            "agent-connector-sdk",
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
                aliases=aliases or {} if e["name"] == "agent-connector-sdk" else {},
            )
            for e in registry
        ]

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(explorer, "load_all", fake_load)
    page = tmp_path / "index.html"
    assert explorer.main(["--mode", "github", "--artifact", str(page)]) == 0
    return page.read_text()


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
    assert hits[0]["repo"] == "agent-connector-sdk" and hits[0]["kind"] == "row"


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
        "agent-webui",
        "Qualify the installed WebUI with real Arbora served operations.",
    )
    tree = Tree(model)
    direct = Placer(tree).run([row])
    where = {r["id"]: nid for nid, rs in direct.items() for r in rs}
    assert where["WEBUI-APPS-R050"] == "webui.apps.accept"
    assert unmapped_violations(tree, direct, []) == []
    assert model["unmapped_allow"] == []
