"""Shared fixtures of the declared documentation gate tests: a loopback site server and fetch."""

from __future__ import annotations

import contextlib
import functools
import http.server
import threading
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest


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


def chrome() -> str:
    """A headless Chromium binary (the harness browser first); a host without one skips the served-site proof."""
    import glob
    import shutil

    for pattern in (
        "/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        str(
            Path.home()
            / ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"
        ),
    ):
        found = sorted(glob.glob(pattern))
        if found:
            return found[-1]
    path = shutil.which("chromium") or shutil.which("google-chrome")
    if not path:
        pytest.skip("headless Chromium is not installed on this host")
    return path


def browse(url: str, *, scheme: str = "light", budget: int = 6000) -> str:
    """The DOM of ``url`` after load, rendered by headless Chrome under ``prefers-color-scheme``."""
    import subprocess

    flags = [
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=1200,900",
        f"--virtual-time-budget={budget}",
        "--dump-dom",
    ]
    if scheme == "dark":
        flags.append("--force-dark-mode")
    done = subprocess.run([chrome(), *flags, url], capture_output=True, text=True, timeout=240, check=True)
    return done.stdout


def probe_of(dom: str) -> dict:
    import html
    import json
    import re

    match = re.search(r'data-probe="([^"]*)"', dom)
    assert match, "the page probe did not run"
    return json.loads(html.unescape(match.group(1)))
