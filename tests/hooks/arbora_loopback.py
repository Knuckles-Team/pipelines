"""A loopback arbora endpoint for the publish and tree-read tests.

It answers the ``POST /ops/<operation>`` shape of the arbora HTTP API with
the ``{"ok": true, "result": ...}`` envelope. Recording operations append to
``records``; ``spec.status`` answers from the states recorded so far, as the
engine does; ``release.rows`` answers the rows of one repository from the published release plans; ``source.tree`` and ``source.blob`` serve one directory.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class Loopback:
    """The recorded traffic and the switches of one fixture endpoint."""

    def __init__(self, tree: Path | None = None, *, fail: bool = False) -> None:
        self.tree = tree
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any], str]] = []
        self.verdicts: list[dict[str, Any]] = []
        self.states: list[dict[str, Any]] = []
        self.release_plans: list[dict[str, Any]] = []
        self.endpoint = ""

    def answer(self, operation: str, params: dict[str, Any]) -> Any:
        if operation == "source.gate_verdict":
            self.verdicts.append(params)
            return {"recorded": True}
        if operation == "source.spec_state":
            self.states.extend(params["records"])
            return {"recorded": len(params["records"])}
        if operation == "source.release_graph":
            self.release_plans.append(params["plan"])
            return {"recorded": len(params["facts"]["inBundle"])}
        if operation == "release.rows":
            return {
                "rows": [
                    rid for plan in self.release_plans for rid in plan["rows_by_repo"].get(params["repository"], [])
                ]
            }
        if operation == "spec.status":
            return {"rows": [{"id": r["id"], "state": r["state"]} for r in self.states if r["kind"] == "row"]}
        if operation == "source.tree" and self.tree is not None:
            return self._tree(params.get("path", ""))
        if operation == "source.blob" and self.tree is not None:
            return self._blob(params["path"])
        return None

    def _tree(self, path: str) -> dict[str, Any]:
        base = self.tree / path if path else self.tree
        if not base.is_dir():
            return {"found": False, "reason": "no such directory", "entries": []}
        entries = []
        for child in sorted(base.iterdir()):
            relative = child.relative_to(self.tree).as_posix()
            if child.is_dir():
                entries.append({"path": relative, "kind": "directory"})
            else:
                digest = "sha256:" + hashlib.sha256(child.read_bytes()).hexdigest()
                entries.append({"path": relative, "kind": "file", "content_digest": digest})
        return {"found": True, "entries": entries}

    def _blob(self, path: str) -> dict[str, Any]:
        target = self.tree / path
        if not target.is_file():
            return {"found": False, "reason": "no such file"}
        data = target.read_bytes()
        return {
            "found": True,
            "content": base64.b64encode(data).decode("ascii"),
            "content_encoding": "base64",
            "size": len(data),
        }


@contextmanager
def serving(state: Loopback) -> Iterator[Loopback]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            params = json.loads(self.rfile.read(length) or b"{}")
            operation = self.path.removeprefix("/ops/")
            state.calls.append((operation, params, self.headers.get("Authorization", "")))
            if state.fail:
                self.send_response(503)
                self.end_headers()
                return
            body = json.dumps({"ok": True, "result": state.answer(operation, params)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.endpoint = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
