"""Publication compares every staged byte without weakening readiness proof."""

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "publication", ROOT / ".github/actions/wheel-readiness/publication.py"
)
publication = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publication)
FILE = "example-1.0-py3-none-any.whl"
EXPECTED = {"package": "example", "version": "1.0", "files": {FILE: "a" * 64}}
URL = "https://pypi.org/pypi/example/1.0/json"


def response(files):
    result = io.StringIO(
        json.dumps({"info": {"name": "example", "version": "1.0"}, "urls": files})
    )
    result.geturl = lambda: URL
    return result


def item(name=FILE, digest="a" * 64):
    return {"filename": name, "digests": {"sha256": digest}}


def test_subset_and_complete():
    with patch.object(publication, "urlopen", return_value=response([])):
        assert publication.missing(EXPECTED) == [FILE]
    with patch.object(publication, "urlopen", return_value=response([item()])):
        assert publication.missing(EXPECTED) == []


@pytest.mark.parametrize(
    "files",
    [
        [item(digest="b" * 64)],
        [item("other.whl")],
        [item(), item()],
        [item(digest=None)],
        [42],
    ],
)
def test_conflicts_fail_immediately(files):
    with (
        patch.object(publication, "urlopen", return_value=response(files)),
        patch.object(publication.time, "sleep") as sleep,
    ):
        with pytest.raises(ValueError):
            publication.postverify(EXPECTED)
        sleep.assert_not_called()


@pytest.mark.parametrize("code", [401, 403, 429, 500])
def test_only_404_is_absence(code):
    with patch.object(
        publication, "urlopen", side_effect=HTTPError(URL, code, "test", {}, None)
    ):
        with pytest.raises(HTTPError):
            publication.missing(EXPECTED)
    with patch.object(
        publication, "urlopen", side_effect=HTTPError(URL, 404, "test", {}, None)
    ):
        assert publication.missing(EXPECTED) == [FILE]


def test_propagation_retry_is_bounded():
    with (
        patch.object(publication, "missing", return_value=[FILE]) as fetch,
        patch.object(publication.time, "sleep") as sleep,
    ):
        with pytest.raises(ValueError):
            publication.postverify(EXPECTED, attempts=3, delay=0)
        assert fetch.call_count == 3
        assert sleep.call_count == 2


def test_staged_files_and_links(tmp_path):
    wheel = tmp_path / FILE
    wheel.write_bytes(b"wheel bytes")
    assert publication.staged(tmp_path, "example", "1.0") == {
        FILE: publication.guard.digest(wheel)
    }
    with pytest.raises(ValueError):
        publication.staged(tmp_path, "example", "2.0")
    wheel.unlink()
    wheel.symlink_to(__file__)
    with pytest.raises(ValueError):
        publication.staged(tmp_path, "example", "1.0")


def test_manifest_binds_execution_and_source(tmp_path, monkeypatch):
    (tmp_path / FILE).write_bytes(b"wheel")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    with patch.object(
        publication.guard,
        "identity",
        return_value={"source_commit": "a" * 40, "contract_commit": "b" * 40},
    ):
        data = publication.manifest(tmp_path, "example", "1.0")
    assert data["GITHUB_RUN_ATTEMPT"] == "2"
    assert data["source_commit"] == "a" * 40
    assert data["contract_commit"] == "b" * 40


@pytest.mark.parametrize("change", ["bytes", "attempt", "source", "contract"])
def test_cli_rejects_staging_or_identity_changes(tmp_path, monkeypatch, change):
    stage = tmp_path / "dist"
    stage.mkdir()
    wheel = stage / FILE
    wheel.write_bytes(b"first bytes")
    saved = tmp_path / "manifest.json"
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    identity = {"source_commit": "a" * 40, "contract_commit": "b" * 40}
    arguments = [
        "publication",
        "preflight",
        "--directory",
        str(stage),
        "--package",
        "example",
        "--version",
        "1.0",
        "--manifest",
        str(saved),
    ]
    with (
        patch.object(publication.guard, "identity", side_effect=lambda: dict(identity)),
        patch.object(publication, "missing", return_value=[FILE]),
    ):
        monkeypatch.setattr("sys.argv", arguments)
        publication.main()
        if change == "bytes":
            wheel.write_bytes(b"changed")
        elif change == "attempt":
            monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
        else:
            identity[change + "_commit"] = "c" * 40
        monkeypatch.setattr("sys.argv", [arguments[0], "missing", *arguments[2:]])
        with pytest.raises(ValueError, match="identity changed"):
            publication.main()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"info": {}, "urls": []},
        {"info": {"name": "example", "version": "1.0"}},
        {"info": {"name": "other", "version": "1.0"}, "urls": []},
    ],
)
def test_malformed_remote_fails(payload):
    result = io.StringIO(json.dumps(payload))
    result.geturl = lambda: URL
    with (
        patch.object(publication, "urlopen", return_value=result),
        pytest.raises(ValueError),
    ):
        publication.missing(EXPECTED)


def test_hardlinks_and_directories_rejected(tmp_path):
    path = tmp_path / FILE
    path.write_bytes(b"bytes")
    (tmp_path / "linked.whl").hardlink_to(path)
    with pytest.raises(ValueError):
        publication.staged(tmp_path, "example", "1.0")
    (tmp_path / "linked.whl").unlink()
    path.unlink()
    path.mkdir()
    with pytest.raises(ValueError):
        publication.staged(tmp_path, "example", "1.0")


def test_redirected_404_is_not_absence():
    error = HTTPError("https://another.example/json", 404, "test", {}, None)
    with patch.object(publication, "urlopen", side_effect=error), pytest.raises(ValueError):
        publication.missing(EXPECTED)
