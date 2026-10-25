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
from urllib.request import urlopen
from xml.etree import ElementTree

from .build import DOC_HEAD, DOC_TAIL, HERE, template_source

SOURCE = "https://knuckles-team.github.io/.github/architecture/"
PROBE = """<script>
setTimeout(()=>{
  const e=document.createElement('output'); e.hidden=true; e.id='visual-evidence';
  e.dataset.selected=window.__arch.selected;
  e.dataset.theme=document.documentElement.dataset.theme;
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
        "Open index.html to test theme/navigation. DOM evidence is gzip-compressed.\n"
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


def capture(chrome: str, output: Path, theme: str, viewport: str, node: str) -> None:
    name = f"{theme}-{viewport.replace(',', 'x')}-{node}"
    with tempfile.TemporaryDirectory(prefix="architecture-chrome-") as profile:
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
            (output / f"{theme}.html").as_uri() + f"#node={node}",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    with gzip.open(output / f"{name}.html.gz", "wt", encoding="utf-8") as compressed:
        compressed.write(result.stdout)
    (output / f"{name}.log").write_text(result.stderr)
    if result.returncode or not (output / f"{name}.png").is_file():
        raise RuntimeError(f"Chrome capture failed for {name}; inspect its log")
    probe = re.search(r'<output[^>]+id="visual-evidence"[^>]*>', result.stdout)
    evidence = probe[0] if probe else ""
    if (
        f'data-selected="{node}"' not in evidence
        or f'data-theme="{theme}"' not in evidence
        or 'data-overflow="false"' not in evidence
    ):
        raise RuntimeError(f"Wrong deep-link selection, theme or horizontal overflow for {name}; inspect DOM")


def verify_browser_results(report: Path) -> None:
    """Fail closed if any expected real-browser case did not pass in the hosted job."""
    expected = {
        "test_a_q_deep_link_lands_on_the_owning_part_in_a_browser",
        "test_expanding_a_row_fetches_its_family_once_and_renders_it_safely",
        "test_footer_links_the_guide_and_front_door_and_only_specified_rows_point_to_the_guide",
        "test_ocean_browser_keyboard_zoom_pan_search_and_camera_history[1440,1000]",
        "test_ocean_browser_keyboard_zoom_pan_search_and_camera_history[390,844]",
    }
    cases = {case.attrib.get("name"): case for case in ElementTree.parse(report).iter("testcase")}
    for name in sorted(expected):
        if name not in cases or any(cases[name].find(tag) is not None for tag in ("skipped", "failure", "error")):
            raise ValueError(f"Required real-browser case did not pass: {name}")
    report.with_name("browser-tests-verified.json").write_text(
        json.dumps({"passed": sorted(expected)}, indent=2) + "\n"
    )


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
        (output / f"{theme}.html").unlink()
    for theme in ("light", "dark"):
        for viewport, node in (("1440,1000", "root"), ("1440,1000", "webui"), ("390,844", "root")):
            capture(chrome, output / "before", theme, viewport, node)
        (output / "before" / f"{theme}.html").unlink()


if __name__ == "__main__":
    main()
