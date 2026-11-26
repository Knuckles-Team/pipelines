"""Build Canopy, the ecosystem architecture explorer.

Usage:
  python -m scripts.architecture_explorer.build --mode github --page site/architecture/index.html
  python -m scripts.architecture_explorer.build --redirect --page site/architecture/index.html
  python -m scripts.architecture_explorer.build --mode local --workspace /path/to/workspace \
      --artifact explorer.html --page index.html

The page needs no runtime layout: every level is laid out here with the pinned
layered layout engine (layout.mjs) and inlined as data.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "scripts.architecture_explorer"

from .code_view import FULL_RECLUSTER_SHARE, attach  # noqa: E402
from .details import write_details  # noqa: E402
from .export import ExportRefused, write_export  # noqa: E402
from .sdd import (  # noqa: E402
    build_cards,
    constitutions,
    family_nodes,
    next_step,
    open_questions,
    search_extra,
)
from .canonical import canonical_model, failure_message, merged_aliases, tag_family_keys  # noqa: E402
from .delivery import aggregate  # noqa: E402
from .geometry import count_crossings  # noqa: E402
from .releases import UNSCHEDULED, load_manifests, load_runs, release_view, row_releases  # noqa: E402
from .place import Placer, Tree, add_dynamic_groups, unmapped_violations, validate_code  # noqa: E402
from .sources import load_all, scan_set  # noqa: E402

HERE = Path(__file__).resolve().parent
RELEASES = HERE.parents[1] / "releases"
NEXT_UP = 25
CQ_BADGES = 8
STATUSES = ("VERIFIED", "LANDED", "SPECIFIED", "RETIRED")
FRONT_DOOR = "https://knuckles-team.github.io/.github/"
CONTRIBUTING = "https://github.com/Knuckles-Team/.github/blob/main/CONTRIBUTING.md"
SKILLS = "https://github.com/Knuckles-Team/universal-skills/tree/main/universal_skills/skills"
ARBORA_DEVELOPMENT = SKILLS + "/arbora-development"
EXPLORER = FRONT_DOOR + "architecture/"
DETAILS_PATTERN = EXPLORER + "spec-details/<repo>/<family>.json"
PIPELINES = "https://github.com/Knuckles-Team/pipelines/blob/main/"
CONSTITUTION = PIPELINES + ".specify/memory/constitution.md"
SPEC_STANDARD = PIPELINES + "reference/spec-standard.md"
BOUNDARIES = PIPELINES + "reference/ecosystem-boundaries.md"
TEMPLATES = "https://github.com/Knuckles-Team/pipelines/tree/main/specs/_template"
CONTRIBUTE_STEPS = (
    f"Constitution: read {CONSTITUTION}. Every plan checks against it.",
    f"Route: pick the owner repository with {BOUNDARIES} and the arbora-development skill, {ARBORA_DEVELOPMENT}. Choose an open (SPECIFIED) row here.",
    "Specify: the spec-intake-wizard and spec-generator skills write specs/<id>/spec.md. It holds user stories, Given/When/Then scenarios, and FR- and SC- labels mapped to row IDs.",
    "Clarify: resolve every [NEEDS CLARIFICATION] marker in spec.md before you plan.",
    "Plan: spec-generator writes plan.md. Add contracts/ for cross-repository seams, data-model.md, quickstart.md, and research.md when unknowns remain.",
    "Tasks: task-planner writes tasks.md. Each line reads - [ ] T001 [P] [US1] <ROW-ID>.",
    "Analyze and checklist: spec-verifier checks consistency and writes checklists/requirements.md.",
    "Implement: sdd-implementer builds each task. Run the repository gates.",
    "Land: open a PR whose commits carry a Spec: <ROW-ID> trailer and a bound test.",
    "Release: landed rows ship in the next release bundle.",
)
DESCRIPTION = f"Canopy shows the whole ecosystem, its specs and its delivery state. Front door and contribution path: {FRONT_DOOR}"
DOC_HEAD = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    f'<meta name="description" content="{DESCRIPTION}">\n'
    f'<link rel="help" href="{CONTRIBUTING}">\n<link rel="start" href="{FRONT_DOOR}">\n'
    "<style>:root{color-scheme:light}body{margin:0}[hidden]{display:none!important}</style>\n"
    "</head>\n<body>\n"
)
DOC_TAIL = "\n</body>\n</html>\n"


# PIPE-PAGES-R047: an edge is one of four types, each named by an existing engine predicate
# (sdd-spec `dependsOn`, software `serves`, sdd-spec `crossesSeam`, sdd `verifiedBy`); the page shows the plain word.
EDGE_TYPES = {
    "dependsOn": "depends on",
    "serves": "serves",
    "consumes": "consumes",  # engine predicate: crossesSeam (the consumer side of a contract)
    "proves": "proves",  # engine predicate: verifiedBy, read from the proving side
}


def typed_edge(edge: list) -> dict:
    """One model edge `[from, to, label, type, rows?]` as a level edge; an unknown type is refused."""
    if len(edge) < 4 or edge[3] not in EDGE_TYPES:
        raise SystemExit(f"architecture model: edge {edge[:3]} needs a type from {sorted(EDGE_TYPES)}")
    rows = edge[4] if len(edge) > 4 else []
    return {"from": edge[0], "to": edge[1], "label": edge[2], "type": edge[3], "rows": rows}


def natkey(text: str) -> list:
    import re

    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def levels_for_layout(tree: Tree) -> list[dict]:
    """Return one layout request per node with children, deepest first."""
    out = []
    for nid in sorted(tree.order, key=lambda x: -tree.nodes[x]["level"]):
        node = tree.nodes[nid]
        if not node["children"] or node.get("fixed_layout"):
            continue
        ids = {c["id"] for c in node["children"]}
        out.append(
            {
                "id": nid,
                "bands": node.get("bands"),
                "direction": node.get("direction"),
                "aspect": node.get("aspect"),
                "children": [
                    {"id": c["id"], "band": c.get("band"), "scale": c.get("scale"), "unmapped": bool(c.get("unmapped"))}
                    for c in node["children"]
                ],
                "edges": [typed_edge(edge) for edge in node.get("edges", []) if edge[0] in ids and edge[1] in ids],
            }
        )
    return out


def run_layout(levels: list[dict]) -> dict:
    proc = subprocess.run(
        ["node", str(HERE / "layout.mjs")],
        input=json.dumps({"levels": levels}),
        capture_output=True,
        text=True,
        cwd=HERE,
        check=False,
    )
    if proc.returncode:
        raise SystemExit(f"layout failed: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def spec_entry(r: dict, delivery: dict) -> dict:
    """One spec row on the page: identity, state, and its delivery facts when it has any."""
    entry = {"id": r["id"], "title": r["title"], "status": r["status"], "repo": r["repo"], "family": r["family"]}
    if r["id"] in delivery["scores"]:
        entry["priority"] = delivery["scores"][r["id"]]["priority"]
    cqs = delivery["scores"].get(r["id"], {}).get("cqs", [])
    if cqs:
        entry["cqs"] = cqs[:CQ_BADGES]
    entry["release"] = delivery.get("release_of", {}).get(r["id"], UNSCHEDULED)
    step = delivery.get("row_next", {}).get(r["id"], "")
    if step:
        entry["n"] = step
    count = delivery.get("row_questions", {}).get(r["id"], 0)
    if count:
        entry["q"] = count
    if r["id"] in delivery["frontier_set"]:
        entry["frontier"] = True
    if r["id"] in delivery["unserved_set"]:
        entry["unserved"] = True
    return entry


def page_delivery(delivery: dict, rows: list[dict]) -> dict:
    """The compact delivery block embedded in the page: competency questions, Next up, bundles, and counts."""
    by_id = {r["id"]: r for r in rows}
    nxt = [
        {
            "id": rid,
            "title": by_id[rid]["title"],
            "repo": by_id[rid]["repo"],
            "family": by_id[rid]["family"],
            "priority": delivery["scores"][rid]["priority"],
            "cqs": delivery["scores"][rid]["cqs"][:CQ_BADGES],
        }
        for rid in delivery["frontier"][:NEXT_UP]
    ]
    for bundle in delivery["bundles"]:
        for step in bundle["steps"]:
            for row in step["rows"]:
                row["family"] = by_id[row["id"]]["family"]
    return {
        "questions": delivery["questions"],
        "next": nxt,
        "bundles": delivery["bundles"],
        "counts": {
            "open": len(delivery["scores"]),
            "frontier": len(delivery["frontier"]),
            "unserved": len(delivery["unserved"]),
        },
    }


def emit(node: dict, direct: dict, layouts: dict, delivery: dict) -> dict:
    out = {
        "id": node["id"],
        "label": node["label"],
        "role": node.get("role", ""),
        "level": node["level"],
        "description": node["desc"],
        "layer": node["layer"],
        "repo": node["repo"],
        "code": node.get("code", []),
        "links": node.get("links", []),
        "specs": [
            {**spec_entry(r, delivery), **({"desc": r["desc"]} if r.get("desc") else {})}
            for r in sorted(direct.get(node["id"], []), key=lambda r: natkey(r["id"]))
        ],
        "children": [emit(c, direct, layouts, delivery) for c in node["children"]],
    }
    for key in ("tools", "unmapped", "external"):
        if node.get(key):
            out[key] = node[key]
    if node["id"] in layouts:
        out["layout"] = layouts[node["id"]]
    return out


def search_index(data: dict, aliases: dict[str, str] | None = None) -> dict:
    """Return the compact capability-search index for the placed tree.

    Every spec row is `[id, title, node, repo, family, status]` (numbers index the shared tables) and
    every node is `[id, label, description, repo, code paths]`; `aliases` maps retired IDs and prefixes
    from each repository's `.config/spec-aliases.toml` to their canonical form.
    """
    repos: dict[str, int] = {}
    fams: dict[str, int] = {}

    def intern(table: dict[str, int], key: str) -> int:
        return table.setdefault(key, len(table))

    nodes: list[list] = []
    rows: list[list] = []
    for node in _walk(data):
        idx = len(nodes)
        nodes.append([node["id"], node["label"], node["description"], intern(repos, node["repo"] or ""), node["code"]])
        for spec in node["specs"]:
            rows.append(
                [
                    spec["id"],
                    spec["title"],
                    idx,
                    intern(repos, spec["repo"]),
                    intern(fams, spec["family"]),
                    STATUSES.index(spec["status"]) if spec["status"] in STATUSES else 1,
                ]
            )
    return {
        "v": 1,
        "repos": list(repos),
        "fams": list(fams),
        "st": list(STATUSES),
        "nodes": nodes,
        "rows": rows,
        "aliases": dict(sorted((aliases or {}).items())),
    }


FLEET = "connectors"
DISCOVERED = "conn.discovered"


def fit_fleet(model: dict, scanned: list[dict]) -> None:
    """Make the connector fleet match the scan set.

    A connector part whose repository was not scanned (deleted, archived, or without
    specs) is removed; each newly discovered repository gets a part under
    "Newly discovered repositories" so its rows have a home without a model edit.
    """
    names = {e["name"] for e in scanned}
    fleet = next((c for c in model["children"] if c["id"] == FLEET), None)
    if fleet is None:
        return

    def prune(node: dict) -> None:
        node["children"] = [c for c in node.get("children", []) if not c.get("repo") or c["repo"] in names]
        for child in node["children"]:
            prune(child)

    prune(fleet)
    known = {n.get("repo") for n in _walk(model)}
    new = [e["name"] for e in scanned if e.get("discovered") and e["name"] not in known]
    if new:
        fleet["children"].append(
            {
                "id": DISCOVERED,
                "label": "Newly discovered repositories",
                "role": f"{len(new)} repositories",
                "desc": "Organization repositories with specs that the model does not place yet.",
                "layer": "source",
                "children": [
                    {
                        "id": f"{DISCOVERED}.{name}",
                        "label": name,
                        "role": "repository",
                        "repo": name,
                        "fam": ["*"],
                        "code": [],
                        "layer": "source",
                        "desc": f"The {name} repository. Its spec rows are read from its default branch.",
                        "links": ["sdk", "ar.mcp.mux"],
                    }
                    for name in new
                ],
            }
        )
    fleet["children"] = [d for d in fleet["children"] if d.get("children")]
    for domain in fleet["children"]:
        domain["role"] = f"{sum(1 for c in domain['children'] if c.get('repo'))} connectors"
    total = sum(1 for n in _walk(fleet) if n.get("repo") and not n.get("children"))
    fleet["role"] = f"{total} connectors in {len(fleet['children'])} domains"


def _walk(node: dict):
    yield node
    for child in node.get("children", []):
        yield from _walk(child)


def build(mode: str, workspace: Path | None) -> tuple[dict, dict]:
    data, meta, _ = build_with_sources(mode, workspace)
    return data, meta


def plan_checker(rows: list[dict]):
    """Return the plan-conformance check of the SDD phase: plan text to its findings (PIPE-PAGES-R054.2)."""
    from pipelines_hooks.specs.plan_conformance import check_plan_text, template_text

    template, known = template_text(HERE.parents[1]), {r["id"] for r in rows}
    return lambda text: check_plan_text(text, template, known)


def row_facts(snaps: list, cards: dict, frontier: set) -> tuple[dict, dict]:
    """Return ``(row_next, row_questions)``: the Next-step chip and the open-question count of each row."""
    row_next, row_questions = {}, {}
    for snap in snaps:
        by_family: dict[str, list[dict]] = {}
        for r in snap.rows:
            by_family.setdefault(r["family"], []).append(r)
        for family, fam_rows in by_family.items():
            phase = cards.get(snap.repo, {}).get(family, {}).get("s", 0)
            asked = [
                q for q in open_questions(snap.docs.get(family, {}), snap.files, family) if q["kind"] != "unreadable"
            ]
            named = {}
            for q in asked:
                if q["row"]:
                    named[q["row"]] = named.get(q["row"], 0) + 1
            for r in fam_rows:
                step = next_step(r, phase, r["id"] in frontier)
                if step:
                    row_next[r["id"]] = step
                if named.get(r["id"]):
                    row_questions[r["id"]] = named[r["id"]]
    return row_next, row_questions


def dependency_edges(delivery: dict, row_node: dict[str, str], pair_cap: int = 20) -> list[list]:
    """Return ``[fromNode, toNode, count, pairs]`` for each pair of nodes with a prerequisite row between them."""
    edges: dict[tuple[str, str], list[list[str]]] = {}
    for prerequisite, unblocked in delivery.get("depends_pairs", []):
        a, b = row_node.get(prerequisite), row_node.get(unblocked)
        if a and b and a != b:
            edges.setdefault((a, b), []).append([prerequisite, unblocked])
    return [[a, b, len(pairs), pairs[:pair_cap]] for (a, b), pairs in sorted(edges.items())]


def build_with_sources(
    mode: str,
    workspace: Path | None,
    *,
    source_families: dict | None = None,
    delivery_out: dict | None = None,
    code_graph: Path | None = None,
    full_recluster_share: float = FULL_RECLUSTER_SHARE,
) -> tuple[dict, dict, list]:
    model = json.loads((HERE / "model.json").read_text())
    registry = json.loads((HERE / "registry.json").read_text())
    scanned = scan_set(registry["repositories"], mode, os.environ.get("GITHUB_TOKEN") or None)
    chart = None
    if source_families is None:
        snaps = load_all(scanned, mode, workspace)
    else:
        from .story_build import load_build_sources

        snaps, chart = load_build_sources(
            scanned, mode, workspace, source_families, token=os.environ.get("GITHUB_TOKEN", "")
        )
    canonical_model(model, merged_aliases(snaps))
    tag_family_keys(snaps)
    fit_fleet(model, scanned)
    rows = [r for s in snaps for r in s.rows]
    tree = Tree(model)
    dropped = validate_code(tree, {s.repo: s.files for s in snaps})
    add_dynamic_groups(tree, rows)
    placer = Placer(tree)
    direct = placer.run(rows)
    layouts = run_layout(levels_for_layout(tree))
    for nid, node in tree.nodes.items():
        if node.get("fixed_layout"):
            layouts[nid] = node["fixed_layout"]
    delivery = aggregate(rows)
    delivery["frontier_set"], delivery["unserved_set"] = set(delivery["frontier"]), set(delivery["unserved"])
    manifests = load_manifests(RELEASES, required=mode == "github")
    delivery["release_of"] = row_releases(manifests, rows)
    delivery["depends_pairs"] = [[d, r["id"]] for r in rows for d in r.get("depends_on", ())]
    cards = build_cards(snaps, delivery["release_of"], {m["id"]: m["phase"] for m in manifests}, plan_checker(rows))
    delivery["cards"] = cards
    delivery["row_next"], delivery["row_questions"] = row_facts(snaps, cards, delivery["frontier_set"])
    data = emit(tree.root, direct, layouts, delivery)
    for repo, summary in attach(snaps, code_graph, full_recluster_share).items():
        for node in _walk(data):
            if node.get("repo") == repo and not node.get("children"):
                node["code_view"] = summary
    row_node = {s["id"]: n["id"] for n in _walk(data) for s in n["specs"]}
    delivery["row_node"] = row_node
    if delivery_out is not None:
        delivery_out.update(delivery)
    data["delivery"] = page_delivery(delivery, rows)
    data["releases"] = release_view(manifests, rows, load_runs(RELEASES), row_node)
    data["cards"] = cards
    data["deps"] = dependency_edges(delivery, row_node)
    unmapped = sum(len(v) for k, v in direct.items() if tree.nodes[k].get("unmapped"))
    violations = unmapped_violations(tree, direct, model.get("unmapped_allow", []))
    meta = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "heads": {s.repo: s.head for s in snaps if s.head},
        "errors": {s.repo: s.error for s in snaps if s.error},
        "slugs": {s.repo: s.slug for s in snaps},
        "owner": registry["owner"],
        "pages_node": registry["pages_node"],
        "rows": len(rows),
        "mapped": len(rows) - unmapped,
        "unmapped": unmapped,
        "unmapped_violations": violations,
        "status": dict(Counter(r["status"] for r in rows)),
        "nodes": len(tree.nodes),
        "depth": max(n["level"] for n in tree.nodes.values()),
        "connectors": sum(1 for e in scanned if e["kind"] == "connector"),
        "families": len({(r["repo"], r["family"]) for r in rows}),
        "how": dict(Counter(placer.how.values())),
        "dropped_code": len(dropped),
        "aliases": {k: v for snap in reversed(snaps) for k, v in snap.aliases.items()},
        "constitutions": constitutions(snaps),
        "crossings": count_crossings(layouts),
    }
    if chart is not None:
        from .story_build import seal_chart

        if meta["errors"] or meta["unmapped_violations"]:
            message = failure_message(meta["errors"], meta["unmapped_violations"])
            if os.environ.get("GITHUB_ACTIONS"):
                print("::error title=architecture build refused::" + message.replace("\n", "%0A"), flush=True)
            raise ValueError(message)
        data["sourceChart"] = seal_chart(chart, built_at=meta["built_at"], snapshots=snaps)
    return data, meta, snaps


def template_source() -> str:
    """Inline licensed font: abstract ocean uses small native SVG/CSS, without a CDN."""
    font = base64.b64encode((HERE / "assets/InterVariable.woff2").read_bytes()).decode("ascii")
    notice = html.escape((HERE / "assets/Inter-LICENSE.txt").read_text()).replace("--", "-&#45;")
    return (
        "<!-- Bundled Inter font copyright and OFL license\n"
        + notice
        + "\n-->\n<!-- Abstract ocean: native vector layers with compositor motion; no photograph or fluid simulation. -->\n"
        + (
            (HERE / "template.html")
            .read_text()
            .replace("/*__INTER__*/", font)
            .replace("/*__SEARCH__*/", (HERE / "search.cjs").read_text())
        )
    )


def template_with_stories(data: dict, meta: dict) -> str:
    """One injection seam for generation and byte-preserving visual previews."""
    from .story_render import render_story

    return template_source().replace("/*__STORY_SCRIPT__*/", render_story(data, meta))


def noscript_block(data: dict, meta: dict) -> str:
    """Return the script-free listing of parts and export links (PIPE-PAGES-R057.7), every value escaped."""
    owner = html.escape(str(meta.get("owner", "")), quote=True)
    slugs = meta.get("slugs", {})
    rows = []
    for node in _walk(data):
        if node["id"] == "root" or not node.get("specs"):
            continue
        families: dict[tuple[str, str], int] = {}
        for spec in node["specs"]:
            key = (spec["repo"], spec["family"])
            families[key] = families.get(key, 0) + 1
        links = []
        for (repo, family), count in sorted(families.items()):
            slug = slugs.get(repo, repo)
            url = f"https://github.com/{owner}/{html.escape(slug, quote=True)}/blob/HEAD/specs/{html.escape(family, quote=True)}/spec.md"
            links.append(f'<a href="{url}">{html.escape(family)}</a> ({count})')
        label = html.escape(node["label"])
        rows.append(f'<tr><th scope="row">{label}</th><td>{len(node["specs"])}</td><td>{", ".join(links)}</td></tr>')
    return (
        '<noscript><section id="noscript-parts" aria-label="Parts and spec rows without scripts">'
        "<h2>Parts and spec rows</h2>"
        "<p>This page draws its map with scripts. Without them, each part lists its own spec rows and spec files. "
        'The same rows are in <a href="export/rows.json">export/rows.json</a> and '
        '<a href="export/rows.md">export/rows.md</a>.</p>'
        '<table><thead><tr><th scope="col">Part</th><th scope="col">Own rows</th><th scope="col">Spec files</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table></section></noscript>"
    )


def render(data: dict, meta: dict) -> str:
    aliases = meta.get("aliases", {})
    meta = {k: v for k, v in meta.items() if k != "aliases"}
    index = search_index(data, aliases)
    payload = json.dumps({"tree": data, "meta": meta, "search": index}, separators=(",", ":")).replace("</", "<\\/")
    page = template_with_stories(data, meta).replace("<!--__NOSCRIPT__-->", noscript_block(data, meta))
    return page.replace("/*__DATA__*/null", payload)


CANONICAL = "https://knuckles-team.github.io/.github/architecture/"
REDIRECT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Canopy — Knuckles-Team ecosystem architecture</title>
<link rel="canonical" href="{url}">
<meta http-equiv="refresh" content="0; url={url}">
<script>location.replace("{url}" + location.hash);</script>
</head>
<body>
<p>The architecture explorer lives at <a href="{url}">{url}</a>.</p>
</body>
</html>
"""


def llms_txt() -> str:
    """Return the plain-text pointer for agents that land on the explorer."""
    lines = [
        "# Canopy: a map of every part and spec row of the ecosystem, with status.",
        f"Front door: {FRONT_DOOR}",
        f"Contribution guide: {CONTRIBUTING}",
        f"Constitution: {CONSTITUTION}",
        f"Spec standard: {SPEC_STANDARD}",
        f"Spec templates: {TEMPLATES}",
        f"Skills: {SKILLS}",
        f"Spec details JSON: {DETAILS_PATTERN}",
        "",
        "How to contribute:",
    ]
    lines += [f"{i}. {step}" for i, step in enumerate(CONTRIBUTE_STEPS, 1)]
    return "\n".join(lines) + "\n"


def redirect_page(url: str = CANONICAL) -> str:
    """Return a page that sends a repository's /architecture/ to the canonical explorer, keeping #<node>."""
    return REDIRECT.format(url=url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("local", "github"), default="github")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--artifact", type=Path, help="write the page body without a document wrapper")
    parser.add_argument("--page", type=Path, help="write a standalone HTML document")
    parser.add_argument("--tree", type=Path, help="write the placed tree and layouts as JSON")
    parser.add_argument(
        "--source-families", type=Path, help="opt-in same-build strict source-family chart configuration"
    )
    parser.add_argument("--code-graph", type=Path, help="directory of per-repository Medulla code-graph snapshots")
    parser.add_argument(
        "--full-recluster-share",
        type=float,
        default=FULL_RECLUSTER_SHARE,
        help="canopy.code_view.full_recluster_share: changed share above which every item is re-clustered",
    )
    parser.add_argument("--redirect", action="store_true", help="write a page that redirects to the canonical explorer")
    args = parser.parse_args(argv)
    if args.redirect:
        if args.source_families:
            parser.error("--redirect cannot qualify source families")
        if not args.page:
            parser.error("--redirect needs --page")
        args.page.parent.mkdir(parents=True, exist_ok=True)
        args.page.write_text(redirect_page())
        return 0
    if args.mode == "local" and not args.workspace:
        parser.error("--workspace is required in local mode")
    full: dict = {}
    if args.source_families:
        from .story_build import read_family_config

        families = read_family_config(args.source_families)
        data, meta, snaps = build_with_sources(
            args.mode,
            args.workspace,
            source_families=families,
            delivery_out=full,
            code_graph=args.code_graph,
            full_recluster_share=args.full_recluster_share,
        )
    else:
        data, meta, snaps = build_with_sources(
            args.mode,
            args.workspace,
            delivery_out=full,
            code_graph=args.code_graph,
            full_recluster_share=args.full_recluster_share,
        )
    body = render(data, meta)
    target = args.page or args.artifact
    if target:
        extra = search_extra(snaps, family_nodes(list(_walk(data))))
        meta["detail_files"] = len(write_details(target.parent, snaps, extra, full))
        try:
            meta["export_files"] = [
                p.relative_to(target.parent).as_posix()
                for p in write_export(target.parent, snaps, [r for s in snaps for r in s.rows], full)
            ]
        except ExportRefused as refused:
            print(f"export refused: {refused}", file=sys.stderr)
            return 1
    for path, text in ((args.artifact, body), (args.page, DOC_HEAD + body + DOC_TAIL)):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if args.page:
        (args.page.parent / "llms.txt").write_text(llms_txt())
    if args.tree:
        args.tree.write_text(json.dumps({"tree": data, "meta": meta}, indent=1))
    print(json.dumps({k: v for k, v in meta.items() if k not in ("heads", "slugs", "pages_node", "aliases")}, indent=1))
    if meta["unmapped_violations"]:
        print("unmapped rows not on the reviewed allowlist: " + ", ".join(meta["unmapped_violations"]), file=sys.stderr)
        return 1
    return 1 if meta["errors"] and args.mode == "github" else 0


if __name__ == "__main__":
    raise SystemExit(main())
