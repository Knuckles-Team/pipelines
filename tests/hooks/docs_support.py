"""Shared fixtures of the declared documentation gate tests: a loopback site server and fetch."""

from __future__ import annotations

import contextlib
import functools
import http.server
import threading
import urllib.request
from collections.abc import Iterator
from pathlib import Path


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


@contextlib.contextmanager
def serve(directory: Path) -> Iterator[str]:
    """Serve ``directory`` on a loopback ephemeral port; yield its base URL."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - loopback only
        return response.read().decode("utf-8")
