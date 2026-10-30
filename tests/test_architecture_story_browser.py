"""Same-build browser pairs cannot silently reuse stale data or a charted baseline."""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.architecture_explorer import story_browser as browser
from scripts.architecture_explorer import story_build as build
from scripts.architecture_explorer.story_contract import ContractError
from test_architecture_story_build import ENTRY, computed_status, fake_api  # noqa: F401 - autouse fixture

pytestmark = pytest.mark.spec("PIPE-PAGES-R042")


def candidate(monkeypatch):
    _, _, request = fake_api()
    monkeypatch.setattr(build, "load_all", lambda *_: [])
    snaps, chart = build.load_build_sources([ENTRY], "github", None, {"pipelines": ["demo"]}, token="", request=request)
    meta = {
        "built_at": "2026-10-26T14:00:00Z",
        "heads": {"pipelines": snaps[0].head},
        "slugs": {"pipelines": "pipelines"},
    }
    build.seal_chart(chart, built_at=meta["built_at"], snapshots=snaps)
    payload = {"tree": {"sourceChart": chart}, "meta": meta, "search": {}}
    script = "const STORY={};function paintStories(){}"
    monkeypatch.setattr(browser, "render_story", lambda *_: script)
    return (
        "const PAYLOAD = "
        + json.dumps(payload)
        + ";\n"
        + script
        + "\npaintAnnotations(); paintStories(); }\nwindow.__storyQA=()=>storyEvidence;"
    )


def test_pair_preserves_actual_payload_removes_only_three_extension_seams(monkeypatch, tmp_path):
    source = candidate(monkeypatch)
    receipt = browser.prepare_pair(source, tmp_path)
    preview = (tmp_path / "preview.html").read_text()
    baseline = (tmp_path / "baseline.html").read_text()
    assert preview == source
    assert browser.extract_payload(preview)[0] == browser.extract_payload(baseline)[0]
    assert "const STORY=" not in baseline and "paintStories();" not in baseline and "__storyQA" not in baseline
    assert "paintAnnotations();" in baseline
    assert receipt["browserQualified"] is False
    assert receipt["kind"] == "same-build-extension-free-rich-browser-pair"


@pytest.mark.parametrize("mutation", ["missing_script", "missing_seam", "stale_hash", "missing_chart"])
def test_invalid_browser_pair_refuses_output(monkeypatch, tmp_path, mutation):
    source = candidate(monkeypatch)
    if mutation == "missing_script":
        source = source.replace("const STORY={};function paintStories(){}", "")
    elif mutation == "missing_seam":
        source = source.replace("window.__storyQA=()=>storyEvidence;", "")
    elif mutation == "stale_hash":
        source = source.replace('"value": 2', '"value": 99')
    elif mutation == "missing_chart":
        source = source.replace('"sourceChart":', '"oldChart":')
    with pytest.raises(ContractError):
        browser.prepare_pair(source, tmp_path)
    assert not (tmp_path / "preview.html").exists()


def test_workflow_requires_current_source_build_and_paired_rich_browser_proof():
    text = (Path(__file__).parents[1] / ".github/workflows/architecture_visual.yml").read_text()
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert "--source-families scripts/architecture_explorer/source-families.json" in text
    assert "--source-file architecture-build/index.html" in text
    assert "scripts.architecture_explorer.story_browser" in text
    assert "--source architecture-build/index.html --output architecture-rich-proof" in text
    assert "architecture-source-proof/current-build-tree.json" in text
    assert "path: architecture-rich-proof/" in text
    assert "path: architecture-source-proof/" in text
    assert "secrets." not in text and "contents: read" in text
