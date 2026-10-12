"""Production publication wiring and read-only release API boundaries."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from urllib.error import URLError

import pytest
import yaml

ROOT = Path(__file__).parents[1]
ACTION = ROOT / ".github/actions/verify-release-source"
REFERENCE = "./.pipeline-contract/.github/actions/verify-release-source"


def load_guard():
    spec = importlib.util.spec_from_file_location("release_api_guard", ACTION / "verify_release_source.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_publisher_checks_tag_before_external_upload():
    python = yaml.safe_load((ROOT / ".github/actions/publish-python-package/action.yml").read_text())
    native = yaml.safe_load((ROOT / ".github/workflows/maturin_pipeline.yml").read_text())
    for steps, upload in [(python["runs"]["steps"], "Publish package"),
                          (native["jobs"]["publish"]["steps"], "Publish to PyPI")]:
        guards = [i for i, step in enumerate(steps) if step.get("uses") == REFERENCE]
        upload_index = next(i for i, step in enumerate(steps) if step.get("name") == upload)
        assert guards == [upload_index - 1]
        assert not steps[guards[0]].get("continue-on-error")
    release = yaml.safe_load((ROOT / ".github/actions/create-version-release/action.yml").read_text())
    steps = release["runs"]["steps"]
    assert steps[-2]["uses"] == REFERENCE and steps[-2]["id"] == "release_source"
    assert steps[-1]["with"]["target_commitish"] == "${{ steps.release_source.outputs.commit }}"
    assert "main" not in steps[-1]["with"].values()
    verifier = yaml.safe_load((ACTION / "action.yml").read_text())
    assert verifier["outputs"]["commit"]["value"] == "${{ steps.verify.outputs.commit }}"
    assert verifier["runs"]["steps"][0]["env"]["EXPECTED_COMMIT"] == "${{ github.sha }}"
    workflow = yaml.safe_load((ROOT / ".github/workflows/python_pipeline.yml").read_text())
    assert workflow["jobs"]["publish-pypi"]["steps"][0]["with"]["ref"] == "${{ github.sha }}"


@pytest.mark.parametrize("origin", ["http://api.github.com", "https://user@api.github.com",
                                   "https://api.github.com/?token=fixture", ""])
def test_api_refuses_unsafe_origins(origin):
    guard = load_guard()
    with pytest.raises(ValueError, match="origin"):
        guard.api_get("/repos/Example/package", {"RELEASE_API_URL": origin})


def test_api_refuses_redirects():
    with pytest.raises(ValueError, match="redirect"):
        load_guard().NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid")


@pytest.mark.parametrize("payload", [b"[" + b" " * (1024 * 1024), b"[]", b"invalid-json"])
def test_invalid_metadata_refuses(monkeypatch, payload):
    guard = load_guard()

    class Transport:
        def open(self, request, *, timeout):
            return io.BytesIO(payload)

    monkeypatch.setattr(guard, "build_opener", lambda *args: Transport())
    with pytest.raises((ValueError, json.JSONDecodeError)):
        guard.api_get("/repos/Example/package",
                      {"RELEASE_API_URL": "https://api.github.com", "RELEASE_TOKEN": "fixture"})


def test_network_failure_writes_no_verified_output(tmp_path, monkeypatch, capsys):
    guard = load_guard()

    def unavailable(environment):
        raise URLError("fixture unavailable")

    monkeypatch.setattr(guard, "verify", unavailable)
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert guard.main() == 1
    assert not output.exists()
    assert "blocked" in capsys.readouterr().err
