"""Build the Arbora Architecture Explorer.

Usage:
  python -m scripts.architecture_explorer.build --mode github --page site/architecture/index.html
  python -m scripts.architecture_explorer.build --mode local --workspace /path/to/workspace \
      --artifact explorer.html --page index.html

The page needs no runtime layout: every level is laid out here with the pinned
layered layout engine (layout.mjs) and inlined as data.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "scripts.architecture_explorer"

from .geometry import count_crossings  # noqa: E402
from .place import Placer, Tree, add_dynamic_groups, unmapped_violations, validate_code  # noqa: E402
from .sources import load_all  # noqa: E402

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


def build(mode: str, workspace: Path | None) -> tuple[dict, dict]:
    model = json.loads((HERE / "model.json").read_text())
    registry = json.loads((HERE / "registry.json").read_text())
    snaps = load_all(registry["repositories"], mode, workspace)
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
        "connectors": sum(1 for e in registry["repositories"] if e["kind"] == "connector"),
        "families": len({(r["repo"], r["family"]) for r in rows}),
        "how": dict(Counter(placer.how.values())),
        "dropped_code": len(dropped),
        "crossings": count_crossings(layouts),
    }
    return data, meta


def render(data: dict, meta: dict) -> str:
    payload = json.dumps({"tree": data, "meta": meta}, separators=(",", ":")).replace("</", "<\\/")
    return (HERE / "template.html").read_text().replace("/*__DATA__*/null", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("local", "github"), default="github")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--artifact", type=Path, help="write the page body without a document wrapper")
    parser.add_argument("--page", type=Path, help="write a standalone HTML document")
    parser.add_argument("--tree", type=Path, help="write the placed tree and layouts as JSON")
    args = parser.parse_args(argv)
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
    print(json.dumps({k: v for k, v in meta.items() if k not in ("heads", "slugs", "pages_node")}, indent=1))
    if meta["unmapped_violations"]:
        print("unmapped rows not on the reviewed allowlist: " + ", ".join(meta["unmapped_violations"]), file=sys.stderr)
        return 1
    return 1 if meta["errors"] and args.mode == "github" else 0


if __name__ == "__main__":
    raise SystemExit(main())
