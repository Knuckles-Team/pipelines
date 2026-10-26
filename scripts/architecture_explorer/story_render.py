"""LOCAL integration proposal: rebuild-derived evidence, never a frozen input file.

Production integration must call this after source-chart sealing and before writes.
The CLI here reads an explicitly supplied generated payload only for validation.
"""

from collections import Counter
import json
from pathlib import Path
import subprocess

from .story_build import verify_chart_receipt

STATES = ("VERIFIED", "LANDED", "SPECIFIED", "RETIRED")


def prepare_models(payload, *, require_source=False):
    models = {}
    node_rows = {}

    def walk(node):
        rows = {(r["repo"], r["id"]): r for r in node["specs"]}
        for child in node["children"]:
            for key, row in walk(child).items():
                if key in rows and rows[key] != row:
                    raise ValueError("conflicting public row identity")
                rows[key] = row
        families = {}
        for row in rows.values():
            families.setdefault(row["repo"] + ":" + row["family"], []).append(row)
        ordered = sorted(families.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        grouped = (
            ordered
            if len(ordered) <= 4
            else ordered[:3] + [(f"{len(ordered) - 3} other families", [r for _, rs in ordered[3:] for r in rs])]
        )
        groups = []
        for key, members in grouped:
            counts = Counter(r["status"] for r in members)
            if set(counts) - set(STATES):
                raise ValueError("unknown public evidence state")
            groups.append(
                {
                    "key": key,
                    "label": key.split(":", 1)[-1].replace("-", " "),
                    "total": len(members),
                    "counts": {s: counts[s] for s in STATES},
                }
            )
        specified = sum(r["status"] == "SPECIFIED" for r in rows.values())
        most = max(ordered, key=lambda pair: sum(r["status"] == "SPECIFIED" for r in pair[1]), default=None)
        takeaway = (
            None
            if not specified
            else {"family": most[0], "count": sum(r["status"] == "SPECIFIED" for r in most[1]), "total": specified}
        )
        models[node["id"]] = {"total": len(rows), "familyCount": len(families), "groups": groups, "takeaway": takeaway}
        node_rows[node["id"]] = rows
        return rows

    all_rows = walk(payload["tree"])
    if len(all_rows) != payload["meta"]["rows"] or len(models) != payload["meta"]["nodes"]:
        raise ValueError("public tree count mismatch")
    # This proposed release explicitly requires the qualified source view. Missing data fails.
    chart = payload["tree"].get("sourceChart")
    if chart is None:
        if require_source:
            raise ValueError("required rebuild source chart absent")
        return {"builtAt": payload["meta"]["built_at"], "evidence": models, "sourceViews": {}, "sourceReceipt": None}
    meta = payload["meta"]
    verify_chart_receipt(chart, built_at=meta["built_at"], public_heads=meta["heads"], public_slugs=meta["slugs"])
    request = {
        "source": chart,
        "index": {repo + ":" + rid: row for (repo, rid), row in all_rows.items()},
        "builtAt": meta["built_at"],
    }
    script = "const fs=require('node:fs');const {buildSourceView}=require(process.argv[1]);const x=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(buildSourceView(x.source,new Map(Object.entries(x.index)),{builtAt:x.builtAt})));"
    run = subprocess.run(
        ["node", "-e", script, str(Path(__file__).with_name("story_view.cjs"))],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
    )
    view = json.loads(run.stdout)
    # Explicit release host: complete selected families must be represented in this node.
    # This does not qualify every capability mapping or convert the scope to whole-node rank.
    for family in view["families"]:
        repo_id, family_id = family["key"].split(":", 1)
        repo = next(r for r in chart["scope"]["repositories"] if r["repositoryId"] == repo_id)["fullName"].split("/")[1]
        matching = [r for (slug, _), r in node_rows["webui"].items() if slug == repo and r["family"] == family_id]
        if len(matching) != family["total"] or any(
            sum(r["status"] == state for r in matching) != count for state, count in family["counts"].items()
        ):
            raise ValueError("selected source family is not complete inside release host")
    return {
        "builtAt": meta["built_at"],
        "evidence": models,
        "sourceViews": {"webui": view},
        "sourceReceipt": chart["buildReceipt"],
    }


def render_story(data, meta):
    """Bounded derived models only; source validation completes before HTML writes."""
    models = prepare_models({"tree": data, "meta": meta})
    script = Path(__file__).with_name("story_canvas.js").read_text()
    evidence = json.dumps(models["evidence"], separators=(",", ":")).replace("</", "<\\/")
    source = json.dumps(models["sourceViews"].get("webui"), separators=(",", ":")).replace("</", "<\\/")
    return "const STORY=" + evidence + ";\nconst SOURCE_VIEW=" + source + ";\n" + script
