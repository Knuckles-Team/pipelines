"""Build a Canopy fixture site, serve it on loopback and drive it in a headless browser (PIPE-PAGES-R053 to R058)."""

from __future__ import annotations

import functools
import http.server
import json
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from test_architecture_explorer import PKG, _chrome, explorer
from scripts.architecture_explorer.sources import Snapshot

FAMILY = "scion-connector-control"
PREFIX = "SCION-CONNECTOR-CONTROL"
DRIVER = Path(__file__).parent / "canopy_drive.cjs"
NEEDS_BROWSER = pytest.mark.skipif(
    shutil.which("node") is None or not (PKG / "node_modules/elkjs").exists() or _chrome() is None,
    reason="the layout engine or a headless Chromium is not installed",
)

CONN = "connector-identity"
ADGUARD = "CONN-ADGUARD-HOME-AGENT"
ANSIBLE = "CONN-ANSIBLE-TOWER-MCP"
TASKS = "".join(
    f"- [{'x' if done else ' '}] T{n:03d} {PREFIX}-R{rid} do the work\n"
    for n, (rid, done) in enumerate((("030", True), ("030", False), ("043", False), ("050", True), ("060", False)), 1)
)
RESEARCH = f"# Research\n\n## Open questions\n\n- [ ] How long is the cutoff for {ANSIBLE}-R002?\n- [ ] Which transport first for {ANSIBLE}-R002?\n"
SDK_DOCS = {
    FAMILY: {
        "spec.md": "# Connector control\n\nThe client rows.\n",
        "plan.md": "# Plan\n\nDelivery phase: P1\n",
        "tasks.md": TASKS,
    }
}


def row(
    rid: str, title: str, status: str = "SPECIFIED", repo: str = "scion-sdk", family: str = FAMILY, **extra
) -> dict:
    return {
        "id": rid,
        "title": title,
        "status": status,
        "repo": repo,
        "family": family,
        "spec_id": rid.rsplit("-R", 1)[0],
        "text": f"{title} must hold.",
        "req": f"{title} must hold.",
        **extra,
    }


ROWS = {
    "scion-sdk": [
        row(f"{PREFIX}-R030", "SDK provides GraphQL introspection context helpers"),
        row(f"{PREFIX}-R043", "SDK declares a source access contract", depends_on=[f"{PREFIX}-R030"]),
        row(f"{PREFIX}-R050", "SDK owns the one client", "VERIFIED"),
        row(f"{PREFIX}-R060", "SDK ships the client", "LANDED"),
    ],
    "adguard-home-agent": [
        row(
            f"{ADGUARD}-R002",
            "Shared GraphQL client",
            repo="adguard-home-agent",
            family=CONN,
            depends_on=[f"{PREFIX}-R030"],
        )
    ],
    "ansible-tower-mcp": [row(f"{ANSIBLE}-R002", "Shared GraphQL client", repo="ansible-tower-mcp", family=CONN)],
}
DOCS = {
    "scion-sdk": SDK_DOCS,
    "adguard-home-agent": {CONN: {"spec.md": "# Identity\n\nClean.\n", "plan.md": "# Plan\n\nBAD plan.\n"}},
    "ansible-tower-mcp": {CONN: {"spec.md": "# Identity\n\nThe cutoff is open.\n", "research.md": RESEARCH}},
}


def node_of(site: Path, row_id: str) -> str:
    """The id of the part that holds ``row_id`` in the built page."""

    def walk(n: dict):
        for spec in n["specs"]:
            if spec["id"] == row_id:
                return n["id"]
        for child in n["children"]:
            found = walk(child)
            if found:
                return found
        return None

    return walk(payload(site)["tree"])


def manifest(rel_id: str, phase: str, roots: list[str]) -> dict:
    return {
        "id": rel_id,
        "name": f"Release {rel_id}",
        "phase": phase,
        "scenario": "S-1",
        "scope": [{"repo": "scion-sdk", "spec": PREFIX, "roots": roots}],
    }


def build_site(monkeypatch, tmp_path: Path, rows=None, docs=None, manifests=None) -> Path:
    """Build the page, its spec details and its export into ``tmp_path / site`` through ``build.main``."""
    rows_by_repo = ROWS if rows is None else rows
    docs_by_repo = DOCS if docs is None else docs

    def fake_load(registry, mode, workspace=None, workers=12):
        out = []
        for e in registry:
            docs_here = docs_by_repo.get(e["name"], {})
            files = {f"specs/{fam}/{name}" for fam, d in docs_here.items() for name in d}
            files |= {f"specs/{r['family']}/requirements.md" for r in rows_by_repo.get(e["name"], [])}
            out.append(
                Snapshot(
                    repo=e["name"],
                    slug=e["slug"],
                    head="h",
                    rows=rows_by_repo.get(e["name"], []),
                    files=files,
                    docs=docs_here,
                )
            )
        return out

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(explorer, "load_all", fake_load)
    # The plan-conformance gate has its own tests; here a plan that says BAD is the only one that fails it.
    monkeypatch.setattr(explorer, "plan_checker", lambda rows: lambda plan: ["bad plan"] if "BAD" in plan else [])
    if manifests is not None:
        releases = tmp_path / "releases"
        releases.mkdir()
        for m in manifests:
            (releases / f"{m['id']}.yml").write_text(json.dumps(m))
        monkeypatch.setattr(explorer, "RELEASES", releases)
    site = tmp_path / "site"
    site.mkdir()
    assert explorer.main(["--mode", "github", "--page", str(site / "index.html")]) == 0
    return site


def payload(site: Path) -> dict:
    page = (site / "index.html").read_text()
    start = page.index("const PAYLOAD = ") + len("const PAYLOAD = ")
    return json.loads(page[start : page.index(";\n(function(){", start)].replace("<\\/", "</"))


@contextmanager
def serve(directory: Path) -> Iterator[str]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def drive(tmp_path: Path, url: str, script: str, *, scripting: bool = True) -> dict:
    """Load ``url`` in headless Chrome, run the async script body and return its JSON result; page errors fail."""
    source = tmp_path / "drive.js"
    source.write_text(script)
    env = {**os.environ, **({} if scripting else {"CANOPY_NO_SCRIPT": "1"})}
    out = subprocess.run(
        ["node", str(DRIVER), _chrome(), url, str(source)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    report = json.loads(out.stdout.strip().split("\n")[-1])
    assert "failure" not in report, report
    assert report["errors"] == [], report["errors"]
    return report["result"]
