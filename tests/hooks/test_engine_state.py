"""compare_engine_state: generated spec status against the engine's served state (PIPE-CONNSPEC-R009)."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.specs.engine_state import compare_engine_state
from pipelines_hooks.specs.generator import generate
from tests.hooks.conftest import Repo

_ROWS = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R001` | **Landed.** |\n| `TEST-R002` | **Open.** |\n"


@contextmanager
def _endpoint(body: bytes) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/spec.status"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _served(**states: str) -> bytes:
    return json.dumps(
        {"rows": [{"id": rid.replace("_", "-"), "state": state} for rid, state in states.items()]}
    ).encode()


def _fixture_repo(repo: Repo) -> dict[Path, dict]:
    repo.commit({"specs/demo/requirements.md": _ROWS}, "add spec")
    repo.commit({"pkg/feature.py": "# implements TEST-R001\n"}, "Spec: TEST-R001")
    return generate(repo.root, "HEAD")


@pytest.mark.spec("PIPE-CONNSPEC-R009.1")
def test_difference_names_rows(repo: Repo) -> None:
    generated = _fixture_repo(repo)
    with _endpoint(_served(TEST_R001="VERIFIED", TEST_R002="SPECIFIED")) as url:
        assert compare_engine_state(generated, url) == ["TEST-R001"]
    with _endpoint(_served(TEST_R001="LANDED")) as url:
        # A row only one side holds counts as a difference.
        assert compare_engine_state(generated, url) == ["TEST-R002"]


@pytest.mark.spec("PIPE-CONNSPEC-R009.1")
def test_an_unreachable_or_malformed_endpoint_cannot_run(repo: Repo) -> None:
    generated = _fixture_repo(repo)
    with pytest.raises(CannotRun):
        compare_engine_state(generated, "file:///etc/hostname")
    with _endpoint(b"not json") as url, pytest.raises(CannotRun):
        compare_engine_state(generated, url)
    with _endpoint(b"{}") as url, pytest.raises(CannotRun):
        compare_engine_state(generated, url)
    with _endpoint(b"{}") as url:
        dead = url.replace(url.rsplit(":", 1)[1].split("/")[0], "1")
    with pytest.raises(CannotRun):
        compare_engine_state(generated, dead)


@pytest.mark.spec("PIPE-CONNSPEC-R009.2")
def test_generator_and_engine_agree(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    generated = _fixture_repo(repo)
    with _endpoint(_served(TEST_R001="LANDED", TEST_R002="SPECIFIED")) as url:
        assert compare_engine_state(generated, url) == []
        assert repo.run("spec-status", "--engine-endpoint", url) == 0
    capsys.readouterr()
    with _endpoint(_served(TEST_R001="LANDED", TEST_R002="LANDED")) as url:
        assert repo.run("spec-status", "--engine-endpoint", url) == 1
    out = capsys.readouterr().out
    assert "FAIL:" in out
    assert "TEST-R002" in out
    assert "TEST-R001" not in out
