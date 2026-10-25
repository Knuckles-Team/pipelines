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

    dom = f'<output id="visual-evidence" data-selected="root" data-theme="{theme}" data-overflow="false"></output>'
    (tmp_path / "light-390x844-root.png").write_bytes(b"pixel-fixture")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=dom, stderr=""))
    if theme == "dark":
        with pytest.raises(RuntimeError, match="theme"):
            capture("chrome", tmp_path, "light", "390,844", "root")
    else:
        capture("chrome", tmp_path, "light", "390,844", "root")
    with gzip.open(tmp_path / "light-390x844-root.html.gz", "rt") as compressed:
        assert compressed.read() == dom
    assert not (tmp_path / "light-390x844-root.html").exists()
