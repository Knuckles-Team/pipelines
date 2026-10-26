"""Read-only PR preview: current public payload, candidate template, runner Chrome."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
from urllib.request import urlopen
from xml.etree import ElementTree

from .build import DOC_HEAD, DOC_TAIL, HERE, template_source

SOURCE = "https://knuckles-team.github.io/.github/architecture/"
PROBE = """<script>
setTimeout(async()=>{
  await document.fonts.ready;
  const bundled=[...document.querySelectorAll('style')].some(style=>style.textContent.includes('@font-face'));
  const faces=bundled?await document.fonts.load('500 14px Inter'):[];
  const interLoaded=faces.some(face=>face.family.replaceAll('\"','').replaceAll("'",'')==='Inter'&&face.status==='loaded');
  const e=document.createElement('output'); e.hidden=true; e.id='visual-evidence';
  e.dataset.selected=window.__arch.selected;
  e.dataset.theme=document.documentElement.dataset.theme;
  e.dataset.fonts=String(document.fonts.status==='loaded');
  e.dataset.inter=interLoaded?'loaded':'absent';
  e.dataset.overflow=String(document.documentElement.scrollWidth>innerWidth);
  e.textContent=JSON.stringify({selected:window.__arch.selected,cam:window.__arch.cam,
    visible:window.__arch.visible(),viewport:[innerWidth,innerHeight],
    background:getComputedStyle(document.documentElement).getPropertyValue('--sheet')});
  document.body.append(e);
},1000);
</script>"""


def extract_payload(source: str) -> tuple[str, dict]:
    """Validate JSON but preserve its original bytes/escaping, never reserialize it."""
    match = re.search(r"const PAYLOAD = (.*?);\n", source)
    if not match:
        raise ValueError("public page has no single-line architecture payload")
    raw = match[1]
    if "</script" in raw.lower():
        raise ValueError("payload contains an unsafe HTML script terminator")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not all(
        isinstance(payload.get(key), dict) for key in ("tree", "meta", "search")
    ):
        raise ValueError("payload must contain tree, meta and search objects")
    return raw, payload


def prepare_preview(source: str, output: Path, candidate: str) -> dict:
    raw, payload = extract_payload(source)
    template = (HERE / "template.html").read_text()
    page = template_source().replace("/*__DATA__*/null", raw)
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(DOC_HEAD + page + DOC_TAIL)
    (output / "README.txt").write_text(
        "Visual/navigation preview only. Spec detail shards are not included; expand-detail offline is unavailable.\n"
        "The canonical deployed generator and its full detail behavior are unchanged.\n"
        "Open the exact, complete index.html to test theme/navigation.\n"
        "Gzipped DOM diagnostics are COMPACTED, not raw or replayable HTML. Duplicate PAYLOAD/font/art\n"
        "are replaced only at known inline locations by SHA256/UTF-8-byte-count markers; per-capture\n"
        "manifests record original DOM hashes and payload equality with the full interactive index.\n"
        "Visible UI, probe attributes, console logs, verdicts and actual PNG pixels are unchanged.\n"
        "Continuous-motion frames are sampled in a real browser at wall-clock intervals without animation seeking; see their JSON evidence, not a synthetic video.\n"
    )
    for theme in ("light", "dark"):
        head = DOC_HEAD.replace('<html lang="en">', f'<html lang="en" data-theme="{theme}">')
        (output / f"{theme}.html").write_text(head + page + PROBE + DOC_TAIL)
    before = output / "before"
    before.mkdir(exist_ok=True)
    for theme in ("light", "dark"):
        original = source.replace('<html lang="en">', f'<html lang="en" data-theme="{theme}">')
        (before / f"{theme}.html").write_text(original.replace("</body>", PROBE + "</body>"))
    evidence = {
        "source_url": SOURCE,
        "source_built_at": payload["meta"].get("built_at"),
        "source_heads": payload["meta"].get("heads"),
        "candidate_sha": candidate,
        "payload_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "template_sha256": hashlib.sha256(template.encode()).hexdigest(),
        "rows": payload["meta"].get("rows"),
        "nodes": payload["meta"].get("nodes"),
    }
    (output / "provenance.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def compact_diagnostic_dom(dom: str, expected_payload_sha256: str) -> tuple[str, dict]:
    """Elide only duplicated inline data; these diagnostics are not replayable HTML."""
    elisions = []

    def record(kind: str, value: str) -> str:
        encoded = value.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        elisions.append({"kind": kind, "sha256": digest, "utf8_bytes": len(encoded)})
        return f"ELIDED {kind} sha256={digest} utf8_bytes={len(encoded)}"

    payload = re.search(r"const PAYLOAD = (.*?);\n", dom)
    if not payload or hashlib.sha256(payload[1].encode()).hexdigest() != expected_payload_sha256:
        raise RuntimeError("Captured DOM payload does not match the exact interactive index")
    compact = dom[: payload.start(1)] + "null/*" + record("PAYLOAD", payload[1]) + "*/" + dom[payload.end(1) :]
    compact = re.sub(
        r"data:(?:font/woff2|image/webp);base64,[A-Za-z0-9+/=]+",
        lambda match: record("inline-data-url", match[0]),
        compact,
    )
    manifest = {
        "kind": "compacted diagnostic DOM, not raw or replayable HTML",
        "original_dom_sha256": hashlib.sha256(dom.encode()).hexdigest(),
        "diagnostic_dom_sha256": hashlib.sha256(compact.encode()).hexdigest(),
        "payload_matches_interactive_index": True,
        "elisions": elisions,
    }
    return compact, manifest


def measure_artifact_size(output: Path) -> None:
    """Fail before publishing oversized proof; never discard pixels or verdicts."""
    with tempfile.TemporaryFile() as compressed:
        with zipfile.ZipFile(compressed, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(output))
        size = compressed.tell()
    (output / "artifact-size.json").write_text(
        json.dumps({"estimated_zip_bytes": size, "limit_bytes": 31 * 1024 * 1024}) + "\n"
    )
    if size > 31 * 1024 * 1024:
        raise RuntimeError("Preview exceeds 31 MiB: split artifacts; do not discard or recompress pixel evidence")


def capture(
    chrome: str,
    output: Path,
    theme: str,
    viewport: str,
    node: str,
    *,
    require_inter: bool = True,
) -> None:
    name = f"{theme}-{viewport.replace(',', 'x')}-{node}"
    with tempfile.TemporaryDirectory(prefix="architecture-chrome-") as profile:
        page = output / f"{theme}.html"
        command = [
            chrome,
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            f"--user-data-dir={profile}",
            f"--window-size={viewport}",
            "--virtual-time-budget=4000",
            "--run-all-compositor-stages-before-draw",
            f"--screenshot={output / (name + '.png')}",
            "--dump-dom",
            page.as_uri() + f"#node={node}",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    (output / f"{name}.log").write_text(result.stderr)
    index = output / "index.html"
    if not index.is_file():
        index = output.parent / "index.html"
    raw, _ = extract_payload(index.read_text())
    try:
        compact, manifest = compact_diagnostic_dom(result.stdout, hashlib.sha256(raw.encode()).hexdigest())
    except RuntimeError:
        # Keep failure evidence intact rather than hide unexpected payload/browser output.
        with gzip.open(output / f"{name}.failed-raw.html.gz", "wt", encoding="utf-8") as failed:
            failed.write(result.stdout)
        raise
    (output / f"{name}.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with gzip.open(output / f"{name}.html.gz", "wt", encoding="utf-8") as compressed:
        compressed.write(compact)
    if result.returncode or not (output / f"{name}.png").is_file():
        raise RuntimeError(f"Chrome capture failed for {name}; inspect its log")
    probe = re.search(r'<output[^>]+id="visual-evidence"[^>]*>', result.stdout)
    evidence = probe[0] if probe else ""
    if (
        f'data-selected="{node}"' not in evidence
        or f'data-theme="{theme}"' not in evidence
        or 'data-overflow="false"' not in evidence
        or 'data-fonts="true"' not in evidence
        or (require_inter and 'data-inter="loaded"' not in evidence)
    ):
        raise RuntimeError(f"Wrong deep-link selection, theme, font or horizontal overflow for {name}; inspect DOM")


def verify_browser_results(report: Path) -> None:
    """Fail closed if any expected real-browser case did not pass in the hosted job."""
    expected = {
        "test_a_q_deep_link_lands_on_the_owning_part_in_a_browser",
        "test_expanding_a_row_fetches_its_family_once_and_renders_it_safely",
        "test_footer_links_the_guide_and_front_door_and_only_specified_rows_point_to_the_guide",
        "test_ocean_browser_keyboard_zoom_pan_search_and_camera_history[1440,1000]",
        "test_ocean_browser_keyboard_zoom_pan_search_and_camera_history[390,844]",
        "test_ocean_browser_motion_controls_and_composited_wave_phases",
        "test_ocean_browser_candidate_model_subtitles_paint_without_overlap",
        "test_ocean_browser_count_text_and_completion_tracks_never_overlap[root-1440,1000]",
        "test_ocean_browser_count_text_and_completion_tracks_never_overlap[root-390,844]",
        "test_ocean_browser_count_text_and_completion_tracks_never_overlap[webui-1440,1000]",
        "test_ocean_browser_count_text_and_completion_tracks_never_overlap[webui-390,844]",
        "test_ocean_browser_count_text_and_completion_tracks_never_overlap[eg-1440,1000]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[default-1440,1000]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[default-390,844]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[root-1440,1000]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[root-390,844]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[webui-1440,1000]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[webui-390,844]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[eg-1440,1000]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[eg-390,844]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[connectors-1440,1000]",
        "test_ocean_browser_annotation_paint_avoids_cards_connectors_and_other_labels[connectors-390,844]",
    }
    cases = {case.attrib.get("name"): case for case in ElementTree.parse(report).iter("testcase")}
    for name in sorted(expected):
        if name not in cases or any(cases[name].find(tag) is not None for tag in ("skipped", "failure", "error")):
            raise ValueError(f"Required real-browser case did not pass: {name}")
    report.with_name("browser-tests-verified.json").write_text(
        json.dumps({"passed": sorted(expected)}, indent=2) + "\n"
    )
    measure_artifact_size(report.parent)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-browser-results", type=Path)
    parser.add_argument("--source-file", type=Path, help="Offline public-page snapshot for local validation")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.verify_browser_results:
        verify_browser_results(args.verify_browser_results)
        return
    if not args.output:
        parser.error("--output is required when creating a preview")
    if args.source_file:
        source = args.source_file.read_text()
    else:
        with urlopen(SOURCE, timeout=60) as response:
            source = response.read(16 * 1024 * 1024).decode("utf-8")
    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    output = args.output.resolve()
    prepare_preview(source, output, candidate)
    if args.prepare_only:
        return
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        raise RuntimeError("Runner Chrome missing; no browser download is permitted by this job")
    (output / "chrome-version.txt").write_text(subprocess.check_output([chrome, "--version"], text=True))
    for theme in ("light", "dark"):
        for viewport in ("1440,1000", "390,844"):
            for node in ("root", "webui", "tui"):
                capture(chrome, output, theme, viewport, node)
        subprocess.run(
            ["node", str(Path(__file__).with_name("motion_capture.cjs")), chrome, str(output), theme],
            check=True,
            timeout=90,
        )
        (output / f"{theme}.html").unlink()
    for theme in ("light", "dark"):
        for viewport, node in (("1440,1000", "root"), ("1440,1000", "webui"), ("390,844", "root")):
            capture(chrome, output / "before", theme, viewport, node, require_inter=False)
        (output / "before" / f"{theme}.html").unlink()
    measure_artifact_size(output)


if __name__ == "__main__":
    main()
