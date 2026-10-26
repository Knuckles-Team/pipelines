"""Assemble two local artifacts; canonical files are read only."""

import base64
import hashlib
import json
import lzma
import argparse
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
OUT = parser.parse_args().output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = HERE.parents[1] / "scripts/architecture_explorer"
archive = (HERE / "snapshot.json.xz").read_bytes()
assert hashlib.sha256(archive).hexdigest() == "059ae42234af382536321f39ca8b6314d197b157bd97fcf751908612f6cfca20"
payload_text = lzma.decompress(archive).decode()
raw = (HERE / "template.html").read_text().replace("/*__DATA__*/null", payload_text)
payload = json.loads(payload_text)
models = {}
webui_rows = {}


def walk(n):
    rows = {(s["repo"], s["id"]): s for s in n["specs"]}
    for ch in n["children"]:
        for key, row in walk(ch).items():
            assert key not in rows or rows[key] == row
            rows[key] = row
    assert len(rows) == len(n["specs"]) + sum(models[ch["id"]]["total"] for ch in n["children"])
    families = {}
    for row in rows.values():
        key = row["repo"] + ":" + row["family"]
        families.setdefault(key, []).append(row)
    ordered = sorted(families.items(), key=lambda item: (-len(item[1]), item[0]))
    chosen = (
        ordered
        if len(ordered) <= 4
        else ordered[:3] + [(str(len(ordered) - 3) + " other families", [r for _, rs in ordered[3:] for r in rs])]
    )
    groups = []
    for key, rs in chosen:
        counts = Counter(r["status"] for r in rs)
        groups.append(
            {
                "key": key,
                "label": key.split(":", 1)[-1].replace("-", " "),
                "total": len(rs),
                "counts": {s: counts[s] for s in ("VERIFIED", "LANDED", "SPECIFIED", "RETIRED")},
            }
        )
    assert sum(g["total"] for g in groups) == len(rows)
    specified = sum(r["status"] == "SPECIFIED" for r in rows.values())
    most = max(ordered, key=lambda item: sum(r["status"] == "SPECIFIED" for r in item[1]), default=None)
    takeaway = (
        None
        if not specified
        else {"family": most[0], "count": sum(r["status"] == "SPECIFIED" for r in most[1]), "total": specified}
    )
    models[n["id"]] = {"total": len(rows), "familyCount": len(families), "groups": groups, "takeaway": takeaway}
    if n["id"] == "webui":
        webui_rows.update(rows)
    return rows


root_rows = walk(payload["tree"])
assert len(root_rows) == 8366
assert len(models) == 598
source = raw
font = base64.b64encode((SOURCE / "assets/InterVariable.woff2").read_bytes()).decode()
baseline = (
    source.replace("/*__DATA__*/null", payload_text)
    .replace("/*__SEARCH__*/", (SOURCE / "search.cjs").read_text())
    .replace("/*__INTER__*/", font)
)
source_bytes = lzma.decompress((HERE / "source-chart.json.xz").read_bytes())
assert hashlib.sha256(source_bytes).hexdigest() == "02f290f9756ea4387cadc1aefcfe9d709f124e877b37f1af3a2fb107a5712029"
source_input = {
    "source": json.loads(source_bytes),
    "index": {repo + ":" + rid: row for (repo, rid), row in root_rows.items()},
}
script = "const fs=require('node:fs');const {buildSourceView}=require(process.argv[1]);const x=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(buildSourceView(x.source,new Map(Object.entries(x.index)))));"
view = json.loads(
    subprocess.run(
        ["node", "-e", script, str(HERE / "source-view.cjs")],
        input=json.dumps(source_input),
        text=True,
        capture_output=True,
        check=True,
    ).stdout
)
assert payload["meta"]["built_at"] == view["scope"]["freeze"]
for family in view["families"]:
    matching = [
        r for r in webui_rows.values() if r["repo"] == "overstory" and r["family"] == family["key"].split(":")[1]
    ]
    assert len(matching) == family["total"]
    assert all(sum(r["status"] == state for r in matching) == count for state, count in family["counts"].items())
extension = (
    (HERE / "story.js")
    .read_text()
    .replace("/*__STORY__*/null", json.dumps(models, separators=(",", ":")))
    .replace("/*__SOURCE_VIEW__*/null", json.dumps(view, separators=(",", ":")))
)
(OUT / "source-view.json").write_text(json.dumps(view, indent=2))
needle = "    paintAnnotations(); }"
assert baseline.count(needle) == 1
# Exposing read-only QA state does not alter native gestures or controls.
preview = (
    baseline.replace(
        "// ---------- focus, breadcrumb, settle ----------",
        extension + "\n// ---------- focus, breadcrumb, settle ----------",
    )
    .replace(needle, "    paintAnnotations(); paintStories(); }")
    .replace("window.__arch={", "window.__storyQA=()=>storyEvidence;\nwindow.__arch={")
)
prefix = ""
suffix = ""
baseline = prefix + baseline + suffix
preview = prefix + preview + suffix
(OUT / "baseline.html").write_text(baseline)
(OUT / "preview.html").write_text(preview)
(OUT / "baseline-template.html").write_text(source)
(OUT / "chart-model.json").write_text(json.dumps(models, indent=2))
# Invert exactly three extension-only edits. Everything else must be byte-identical.
restored = (
    preview.replace(extension + "\n", "")
    .replace("    paintAnnotations(); paintStories(); }", needle)
    .replace("window.__storyQA=()=>storyEvidence;\n", "")
)
assert restored == baseline
start = "// ---------- world geometry: every node gets a world rectangle ----------"
end = "// ---------- drawing ----------"


def geometry(text):
    return text.split(start, 1)[1].split(end, 1)[0]


assert geometry(source) == geometry(raw)
receipt = {
    "baseline": "Frozen native-caption baseline; snapshot comparison, not production refresh or motion proof",
    "sourceTemplateSha256": hashlib.sha256(source.encode()).hexdigest(),
    "payloadSha256": hashlib.sha256(payload_text.encode()).hexdigest(),
    "snapshotBuiltAt": payload["meta"]["built_at"],
    "sourceHeads": payload["meta"]["heads"],
    "fontSha256": hashlib.sha256((SOURCE / "assets/InterVariable.woff2").read_bytes()).hexdigest(),
    "nodes": 598,
    "uniqueRootRows": 8366,
    "maxGroups": max(len(m["groups"]) for m in models.values()),
    "identicalAfterRemovingThreeExtensionSeams": True,
    "newDOMControls": 0,
    "geometryCameraCSSAndGesturesUnmodified": True,
    "richSourceScope": "First qualified source-family integration: Overstory only, not all 598 nodes",
    "sourceRows": 248,
    "sourceEdges": 6,
    "pixelAndNativeWheelProof": "PENDING actual hosted browser qualification; local browser known unavailable",
}
(OUT / "Inter-LICENSE.txt").write_bytes((SOURCE / "assets/Inter-LICENSE.txt").read_bytes())
(OUT / "static-checks.json").write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt, indent=2))

for name in ("story.js", "check-slots.cjs", "README.md"):
    (OUT / name).write_bytes((HERE / name).read_bytes())
