"""Qualify rich charts against an extension-free baseline from the same actual build."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from .story_build import verify_chart_receipt
from .story_contract import require
from .story_render import render_story
from .visual_preview import extract_payload


def prepare_pair(source: str, output: Path) -> dict:
    raw, payload = extract_payload(source)
    data, meta = payload["tree"], payload["meta"]
    require("sourceChart" in data, "rich browser proof requires actual same-build source chart")
    verify_chart_receipt(
        data["sourceChart"], built_at=meta["built_at"], public_heads=meta["heads"], public_slugs=meta["slugs"]
    )
    injected = render_story(data, meta)
    require(source.count(injected) == 1, "candidate story injection mismatch")
    baseline = source.replace(injected, "", 1)
    for seam in (" paintStories();", "window.__storyQA=()=>storyEvidence;"):
        require(baseline.count(seam) == 1, "candidate native story seam mismatch")
        baseline = baseline.replace(seam, "", 1)
    require(extract_payload(baseline)[0] == raw, "baseline changed source payload")
    output.mkdir(parents=True, exist_ok=True)
    (output / "preview.html").write_text(source)
    (output / "baseline.html").write_text(baseline)
    receipt = {
        "kind": "same-build-extension-free-rich-browser-pair",
        "builtAt": meta["built_at"],
        "sourceReceipt": data["sourceChart"]["buildReceipt"],
        "payloadSha256": hashlib.sha256(raw.encode()).hexdigest(),
        "candidateHtmlSha256": hashlib.sha256(source.encode()).hexdigest(),
        "baselineHtmlSha256": hashlib.sha256(baseline.encode()).hexdigest(),
        "removedSeams": ["exact generated story script", "paintStories call", "storyQA exposure"],
        "browserQualified": False,
    }
    (output / "input-proof.json").write_text(json.dumps(receipt, indent=2))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    prepare_pair(args.source.read_text(), args.output)
    if args.prepare_only:
        return
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    require(chrome is not None, "runner browser required; no download fallback")
    subprocess.run(
        ["node", str(Path(__file__).with_name("story_capture.cjs")), chrome, str(args.output.resolve())],
        check=True,
        timeout=900,
    )
    receipt = json.loads((args.output / "input-proof.json").read_text())
    receipt["browserQualified"] = True
    receipt["proofSha256"] = hashlib.sha256((args.output / "native-proof.json").read_bytes()).hexdigest()
    (args.output / "input-proof.json").write_text(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
