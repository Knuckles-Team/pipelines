"""Run the real pinned resolver against an in-memory HTTP fixture, never a socket.

This adapter exists only in tests. Production has no fixture/index override.
The actual request/preparation restrictions and pip resolver are left intact.
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from pip._internal.network.session import PipSession
from pip._vendor.requests import Response


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    action, scenario_path = map(Path, sys.argv[1:])
    scenario = json.loads(scenario_path.read_text())
    requests = []

    def fixture_send(self, request, **kwargs):
        requests.append(request.url)
        record = scenario["responses"].get(request.url)
        if record is None:
            raise AssertionError("unexpected network attempt: " + request.url)
        response = Response()
        response.status_code = record.get("status", 200)
        response.url = request.url
        response.request = request
        payload = base64.b64decode(record["body"])
        response.raw = io.BytesIO(payload)
        response.headers.update({"Content-Type": record["type"], "Content-Length": str(len(payload))})
        response.headers.update(record.get("headers", {}))
        return response

    PipSession.send = fixture_send
    guard = load(action / "readiness.py")
    resolver = load(action / "resolve.py")
    wheel = Path(scenario["root"])
    report = scenario_path.parent / "report.json"
    try:
        root = guard.metadata(wheel)
        profile = scenario.get("profile", "base")
        target = str(wheel) + ("[" + profile + "]" if profile != "base" else "")
        operation = (["--target", str(scenario_path.parent / "installed")]
                     if scenario.get("install") else ["--dry-run"])
        result = resolver.run([
            "install", *operation, "--ignore-installed", "--no-cache-dir", "--disable-pip-version-check",
            "--no-input", "--only-binary=:all:", "--index-url", guard.PUBLIC_INDEX,
            "--report", str(report), target,
        ], wheel)
        if result:
            return result
        data = json.loads(report.read_text())
        guard.validate_report(data, wheel, root, profile)
        (scenario_path.parent / "validated.json").write_text(json.dumps(data))
        return 0
    finally:
        (scenario_path.parent / "requests.json").write_text(json.dumps(requests))


if __name__ == "__main__":
    raise SystemExit(main())
