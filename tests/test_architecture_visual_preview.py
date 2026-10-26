"""Read-only visual previews retain source payload bytes and bounded CI authority."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.architecture_explorer.visual_preview import extract_payload, prepare_preview

ROOT = Path(__file__).parents[1]
RAW = r'{"tree":{"label":"A \/ B \\ path"},"meta":{"built_at":"2026-01-01","rows":1},"search":{}}'


@pytest.mark.spec("PIPE-PAGES-R042")
def test_visual_preview_preserves_raw_json_escaping_and_records_provenance(tmp_path: Path) -> None:
    source = f"<script>const PAYLOAD = {RAW};\n</script>"
    raw, payload = extract_payload(source)
    assert raw == RAW and payload["tree"]["label"] == "A / B \\ path"
    evidence = prepare_preview(source, tmp_path, "candidate-commit")
    assert evidence["payload_sha256"] == hashlib.sha256(RAW.encode()).hexdigest()
    assert evidence["candidate_sha"] == "candidate-commit"
    assert evidence["source_built_at"] == "2026-01-01"
    assert json.loads((tmp_path / "provenance.json").read_text()) == evidence
    for name in ("index.html", "light.html", "dark.html"):
        html = (tmp_path / name).read_text()
        assert f"const PAYLOAD = {RAW};\n" in html
        assert "/*__SEARCH__*/" not in html
    assert 'data-theme="dark"' in (tmp_path / "dark.html").read_text()
    assert "id='visual-evidence'" in (tmp_path / "light.html").read_text()


@pytest.mark.spec("PIPE-PAGES-R042")
@pytest.mark.parametrize("raw", ["null", "{}", '{"tree":{},"meta":{},"search":[]}', '{"x":"</script>"}'])
def test_visual_preview_rejects_invalid_or_unsafe_payload(raw: str) -> None:
    with pytest.raises(ValueError):
        extract_payload(f"const PAYLOAD = {raw};\n")


@pytest.mark.spec("PIPE-PAGES-R042")
def test_visual_preview_is_read_only_pr_job_with_retained_evidence() -> None:
    workflow = (ROOT / ".github/workflows/architecture_visual.yml").read_text()
    assert "pull_request:" in workflow and "pull_request_target" not in workflow
    assert "contents: read" in workflow and ": write" not in workflow
    assert "persist-credentials: false" in workflow
    assert "secrets." not in workflow and "deploy" not in workflow.replace("deployment", "")
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "test_architecture_explorer.py" in workflow
    assert "command -v google-chrome || command -v chromium" in workflow
    assert "playwright install" not in workflow


@pytest.mark.spec("PIPE-PAGES-R042")
@pytest.mark.parametrize("bad", ["", "skipped", "failure", "error", "missing"])
def test_real_browser_receipt_fails_closed_for_skipped_missing_or_failed_cases(tmp_path: Path, bad: str) -> None:
    from scripts.architecture_explorer.visual_preview import verify_browser_results

    names = [
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
    ]
    cases = [f'<testcase name="{name}"/>' for name in names]
    if bad == "missing":
        cases.pop()
    elif bad:
        cases[-1] = f'<testcase name="{names[-1]}"><{bad}/></testcase>'
    report = tmp_path / "tests.xml"
    report.write_text("<testsuites><testsuite>" + "".join(cases) + "</testsuite></testsuites>")
    if bad:
        with pytest.raises(ValueError, match="Required real-browser case did not pass"):
            verify_browser_results(report)
    else:
        verify_browser_results(report)
        assert json.loads((tmp_path / "browser-tests-verified.json").read_text())["passed"] == sorted(names)


@pytest.mark.spec("PIPE-PAGES-R042")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_capture_compresses_dom_and_rejects_wrong_theme(monkeypatch, tmp_path: Path, theme: str) -> None:
    import gzip
    from types import SimpleNamespace

    from scripts.architecture_explorer.visual_preview import capture

    dom = f'<output id="visual-evidence" data-selected="root" data-theme="{theme}" data-overflow="false" data-fonts="true" data-inter="loaded"></output>'
    dom = '<script>const PAYLOAD = {"tree":{},"meta":{},"search":{}};\n</script>' + dom
    (tmp_path / "index.html").write_text(dom)
    (tmp_path / "light-390x844-root.png").write_bytes(b"pixel-fixture")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=dom, stderr=""))
    if theme == "dark":
        with pytest.raises(RuntimeError, match="theme"):
            capture("chrome", tmp_path, "light", "390,844", "root")
    else:
        capture("chrome", tmp_path, "light", "390,844", "root")
    with gzip.open(tmp_path / "light-390x844-root.html.gz", "rt") as compressed:
        diagnostic = compressed.read()
        assert "ELIDED PAYLOAD sha256=" in diagnostic
        assert dom.split("</script>", 1)[1] in diagnostic
    assert not (tmp_path / "light-390x844-root.html").exists()


@pytest.mark.spec("PIPE-PAGES-R042")
def test_candidate_requires_real_inter_face_but_baseline_records_fallback(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    from scripts.architecture_explorer.visual_preview import capture

    dom = '<output id="visual-evidence" data-selected="root" data-theme="light" data-overflow="false" data-fonts="true" data-inter="absent"></output>'
    dom = '<script>const PAYLOAD = {"tree":{},"meta":{},"search":{}};\n</script>' + dom
    (tmp_path / "index.html").write_text(dom)
    (tmp_path / "light-390x844-root.png").write_bytes(b"pixel-fixture")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=dom, stderr=""))
    with pytest.raises(RuntimeError, match="font"):
        capture("chrome", tmp_path, "light", "390,844", "root")
    capture("chrome", tmp_path, "light", "390,844", "root", require_inter=False)


@pytest.mark.spec("PIPE-PAGES-R042")
def test_diagnostic_compaction_retains_ui_and_records_exact_original_hashes() -> None:
    import hashlib
    from scripts.architecture_explorer.visual_preview import compact_diagnostic_dom

    raw = '{"tree":{},"meta":{},"search":{}}'
    dom = (
        "<style>@font-face{src:url(data:font/woff2;base64,YWJj)}</style><script>const PAYLOAD = "
        + raw
        + ';\n</script><output id="visual-evidence" data-theme="light">PASS</output>'
    )
    compact, manifest = compact_diagnostic_dom(dom, hashlib.sha256(raw.encode()).hexdigest())
    assert raw not in compact and "YWJj" not in compact
    assert '<output id="visual-evidence" data-theme="light">PASS</output>' in compact
    assert manifest["original_dom_sha256"] == hashlib.sha256(dom.encode()).hexdigest()
    assert manifest["diagnostic_dom_sha256"] == hashlib.sha256(compact.encode()).hexdigest()
    assert len(manifest["elisions"]) == 2
    assert manifest["payload_matches_interactive_index"] is True
    with pytest.raises(RuntimeError, match="does not match"):
        compact_diagnostic_dom(dom, "wrong")


@pytest.mark.spec("PIPE-PAGES-R042")
def test_motion_capture_uses_real_elapsed_browser_time_without_seeking() -> None:
    helper = (ROOT / "scripts/architecture_explorer/motion_capture.cjs").read_text()
    assert "--remote-debugging-pipe" in helper
    assert "await delay(2000)" in helper
    assert "Page.captureScreenshot" in helper
    assert "currentTime=" not in helper and "--virtual-time-budget" not in helper
    assert "Math.abs(w.x-frames[i-1].waves[j].x)>8" in helper
    assert "sha256===frames[i-1].sha256" in helper
    runner = (ROOT / "scripts/architecture_explorer/visual_preview.py").read_text()
    assert 'with_name("motion_capture.cjs")' in runner and "check=True" in runner and "timeout=90" in runner


@pytest.mark.spec("PIPE-PAGES-R042")
def test_motion_capture_rejects_pending_calls_and_cleans_profile_after_exit() -> None:
    helper = (ROOT / "scripts/architecture_explorer/motion_capture.cjs").read_text()
    assert "browser.on('error'" in helper and "browser.once('close'" in helper
    assert "rejectPending(error)" in helper
    assert helper.index("await exited;") < helper.index("rmSync(profile,")


@pytest.mark.spec("PIPE-PAGES-R042")
def test_motion_capture_browser_early_exit_is_bounded_and_cleans_profile(tmp_path: Path) -> None:
    import os
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    browser = tmp_path / "exits-immediately"
    browser.write_text("#!/bin/sh\nexit 1\n")
    browser.chmod(0o755)
    result = subprocess.run(
        [node, str(ROOT / "scripts/architecture_explorer/motion_capture.cjs"), str(browser), str(tmp_path), "light"],
        env={**os.environ, "TMPDIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert (tmp_path / "light-continuous-motion.log").is_file()
    assert not list(tmp_path.glob("architecture-motion-*"))


@pytest.mark.spec("PIPE-PAGES-R042")
def test_annotation_navigation_uses_trusted_keyboard_and_real_fullscreen_after_motion() -> None:
    helper = (ROOT / "scripts/architecture_explorer/motion_capture.cjs").read_text()
    assert helper.index("const navigation=") > helper.index("`${theme}-continuous-motion.json`")
    assert "Input.dispatchKeyEvent" in helper and "type:'keyDown',key:'Enter'" in helper
    assert "requestFullscreen().then(()=>true)" in helper and "userGesture:true" in helper
    assert "event.isTrusted" in helper and "after.active!=='annotations'" in helper
    assert "after.selected!==before.selected||after.hash!==before.hash" in helper
    assert "fullBefore.fullscreen!=='wrap'" in helper
    assert "!document.fullscreenElement&&document.activeElement.id==='annotations'" in helper
    assert "`${theme}-annotation-navigation.json`" in helper
    assert "navigation.passed=false" in helper and "throw error;" in helper
    assert "document.fullscreenElement=" not in helper
