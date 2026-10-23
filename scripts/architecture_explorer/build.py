"""Build the Arbora Architecture Explorer.

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

from .geometry import count_crossings  # noqa: E402
from .place import Placer, Tree, add_dynamic_groups, unmapped_violations, validate_code  # noqa: E402
from .sources import load_all, scan_set  # noqa: E402

HERE = Path(__file__).resolve().parent
STATUSES = ("VERIFIED", "LANDED", "SPECIFIED", "RETIRED")
DOC_HEAD = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    "<style>:root{color-scheme:light}body{margin:0}[hidden]{display:none!important}</style>\n"
    "</head>\n<body>\n"
)
DOC_TAIL = "\n</body>\n</html>\n"


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
                "edges": [
                    {"from": a, "to": b, "label": lab} for a, b, lab in node.get("edges", []) if a in ids and b in ids
                ],
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


def emit(node: dict, direct: dict, layouts: dict) -> dict:
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
            {"id": r["id"], "title": r["title"], "status": r["status"], "repo": r["repo"], "family": r["family"]}
            for r in sorted(direct.get(node["id"], []), key=lambda r: natkey(r["id"]))
        ],
        "children": [emit(c, direct, layouts) for c in node["children"]],
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
    model = json.loads((HERE / "model.json").read_text())
    registry = json.loads((HERE / "registry.json").read_text())
    scanned = scan_set(registry["repositories"], mode, os.environ.get("GITHUB_TOKEN") or None)
    snaps = load_all(scanned, mode, workspace)
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
    data = emit(tree.root, direct, layouts)
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
        "crossings": count_crossings(layouts),
    }
    return data, meta


def render(data: dict, meta: dict) -> str:
    aliases = meta.get("aliases", {})
    meta = {k: v for k, v in meta.items() if k != "aliases"}
    index = search_index(data, aliases)
    payload = json.dumps({"tree": data, "meta": meta, "search": index}, separators=(",", ":")).replace("</", "<\\/")
    page = (HERE / "template.html").read_text().replace("/*__SEARCH__*/", (HERE / "search.cjs").read_text())
    return page.replace("/*__DATA__*/null", payload)


CANONICAL = "https://knuckles-team.github.io/.github/architecture/"
REDIRECT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Arbora Architecture Explorer</title>
<link rel="canonical" href="{url}">
<meta http-equiv="refresh" content="0; url={url}">
<script>location.replace("{url}" + location.hash);</script>
</head>
<body>
<p>The architecture explorer lives at <a href="{url}">{url}</a>.</p>
</body>
</html>
"""


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
    parser.add_argument("--redirect", action="store_true", help="write a page that redirects to the canonical explorer")
    args = parser.parse_args(argv)
    if args.redirect:
        if not args.page:
            parser.error("--redirect needs --page")
        args.page.parent.mkdir(parents=True, exist_ok=True)
        args.page.write_text(redirect_page())
        return 0
    if args.mode == "local" and not args.workspace:
        parser.error("--workspace is required in local mode")
    data, meta = build(args.mode, args.workspace)
    body = render(data, meta)
    for path, text in ((args.artifact, body), (args.page, DOC_HEAD + body + DOC_TAIL)):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if args.tree:
        args.tree.write_text(json.dumps({"tree": data, "meta": meta}, indent=1))
    print(json.dumps({k: v for k, v in meta.items() if k not in ("heads", "slugs", "pages_node", "aliases")}, indent=1))
    if meta["unmapped_violations"]:
        print("unmapped rows not on the reviewed allowlist: " + ", ".join(meta["unmapped_violations"]), file=sys.stderr)
        return 1
    return 1 if meta["errors"] and args.mode == "github" else 0


if __name__ == "__main__":
    raise SystemExit(main())
