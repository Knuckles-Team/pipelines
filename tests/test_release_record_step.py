"""The record-release step of the Python release workflow (PIPE-RELEASE-R009.1, R009.2)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_record  # noqa: E402

WORKFLOW = ROOT / ".github/workflows/python_pipeline.yml"


# spec: PIPE-RELEASE-R009.1
def test_workflow_has_record_step_after_publish() -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["publish-pypi"]["steps"]
    names = [step.get("name") for step in steps]
    record = steps[names.index("Record the release")]
    assert names.index("Record the release") == len(steps) - 1
    assert names.index("Record the release") > names.index("Build, publish and release")
    assert "startsWith(github.ref, 'refs/tags/v')" in record["if"]
    assert record["continue-on-error"] is True
    assert "release_record.py" in record["run"]
    inputs = document[True if True in document else "on"]["workflow_call"]["inputs"]
    assert inputs["release-record-url"]["default"] == ""


def _repo_at(path: Path) -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        check=True,
    )
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


class _Sink(BaseHTTPRequestHandler):
    posted: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers["Content-Length"])
        type(self).posted.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        return


# spec: PIPE-RELEASE-R009.2
def test_step_posts_release_with_digests(tmp_path: Path, monkeypatch) -> None:
    sha = _repo_at(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist-sdist").mkdir()
    (tmp_path / "dist/pkg-1.0.0-py3-none-any.whl").write_bytes(b"wheel-bytes")
    (tmp_path / "dist-sdist/pkg-1.0.0.tar.gz").write_bytes(b"sdist-bytes")
    _Sink.posted = []
    server = HTTPServer(("127.0.0.1", 0), _Sink)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {
            "RELEASE_RECORD_URL": f"http://127.0.0.1:{server.server_port}/record",
            "RELEASE_REPOSITORY": "org/pkg",
            "RELEASE_TAG": "v1.0.0",
            "SOURCE_COMMIT": sha,
            "EXPECTED_COMMIT": sha,
            "LATEST_COMMIT": sha,
        }
        monkeypatch.chdir(tmp_path)
        assert release_record.main(environment=env, root=tmp_path) == 0
    finally:
        server.shutdown()
        thread.join()
    assert len(_Sink.posted) == 1
    body = _Sink.posted[0]
    assert body["op"] == "release.record"
    record = body["params"]
    assert (record["repo"], record["version"], record["git_ref"]) == ("pkg", "1.0.0", "refs/tags/v1.0.0")
    assert record["changeset_head"] == sha and isinstance(record["published_at"], int)
    assert record["artifact_digests"] == sorted(
        [
            f"sha256:{hashlib.sha256(b'wheel-bytes').hexdigest()}",
            f"sha256:{hashlib.sha256(b'sdist-bytes').hexdigest()}",
        ]
    )


def test_failure_marks_the_run_and_no_endpoint_skips(tmp_path: Path, capsys) -> None:
    assert release_record.main(environment={}, root=tmp_path) == 0
    assert "skipped" in capsys.readouterr().out
    assert release_record.main(environment={"RELEASE_RECORD_URL": "http://127.0.0.1:9/x"}, root=tmp_path) == 1


# spec: PIPE-RELEASE-R019
def test_connector_record_carries_the_content_digest_and_must_be_recorded(tmp_path: Path, capsys, monkeypatch) -> None:
    sha = _repo_at(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "pkg"\n', encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist/pkg-1.0.0-py3-none-any.whl").write_bytes(b"wheel-bytes")
    digests = tmp_path / "release-digests.json"
    content = "content-sha256:" + "ab" * 32
    digests.write_text(json.dumps({"artifact_digests": [content]}), encoding="utf-8")
    env = {
        "RELEASE_TAG": "v1.0.0",
        "SOURCE_COMMIT": sha,
        "EXPECTED_COMMIT": sha,
        "LATEST_COMMIT": sha,
        "RELEASE_DIGESTS_FILE": str(digests),
    }
    record = release_record.build_record(env, tmp_path)
    assert content in record["artifact_digests"] and len(record["artifact_digests"]) == 2
    assert release_record.main(environment=env, root=tmp_path) == 1  # no endpoint: refused, not skipped
    assert "must be recorded" in capsys.readouterr().err
