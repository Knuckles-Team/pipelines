"""The published plan reaches the engine: refusal while arbora does not serve the release graph (PIPE-RELEASE-R025.7).

Row R025.7 stays unbound: it needs an arbora ``source.*`` operation that ingests the release graph, and no served
operation does that yet (see the gap note). This test holds the unavailable state against a loopback endpoint that
answers like arbora does for an operation it does not serve.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_plan as rp  # noqa: E402
from scripts import release_scope as rs  # noqa: E402
from tests.test_release_plan import two_project_rows  # noqa: E402


class _Refusing(BaseHTTPRequestHandler):
    seen: list[str] = []

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append(body["op"])
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b'{"code": "OPERATION_UNKNOWN"}')

    def log_message(self, *args: object) -> None:
        return


def test_publish_to_an_endpoint_that_does_not_serve_the_release_graph_is_refused() -> None:
    rows = two_project_rows()
    plan = rp.render_plan(rs.manifest("P1", ["Q-B-R001"], rows), rows)
    server = HTTPServer(("127.0.0.1", 0), _Refusing)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(HTTPError) as refused:
            rp.publish_plan(rp.facts_of(plan, rows), plan, f"http://127.0.0.1:{server.server_port}/ops")
    finally:
        server.shutdown()
        thread.join()
    assert refused.value.code == 404 and _Refusing.seen == [rp.OPERATION]
