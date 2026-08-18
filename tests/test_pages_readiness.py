"""Focused TCKs for CONCEPT:ECO-4.DOCS-DELIVERY.

The fixtures model the canonical universal-skills readiness and Markdown mirror
artifacts; they do not introduce a second production manifest or generator.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import mimetypes
import sys
import threading
from functools import partial
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pytest

# Keep the repository-local helper ahead of any similarly named installed
# package when pytest uses its importlib test mode.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import pages_readiness


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": pages_readiness.SCHEMA_ID,
    "title": "Agent Readiness Applicability",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "project",
        "applicability",
        "standards",
        "content_signals",
        "budgets",
        "capabilities",
    ],
    "properties": {
        "schema_version": {"const": pages_readiness.SCHEMA_VERSION},
        "project": {},
        "applicability": {},
        "standards": {},
        "content_signals": {},
        "budgets": {},
        "capabilities": {},
    },
}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _readiness() -> dict[str, Any]:
    return {
        "schema_version": pages_readiness.SCHEMA_VERSION,
        "project": {"name": "fixture", "kind": "docs-only"},
        "applicability": {
            "content": True,
            "discoverability": True,
            "access_policy": True,
            "capabilities": False,
            "errors": False,
            "provenance": True,
            "measurement": False,
            "deployment": False,
        },
        "standards": [{"id": "Docs Draft", "kind": "draft", "level": "draft"}],
        "content_signals": {"policy": "unset"},
        "budgets": {"curated_chars": 12000, "summary_chars": 500, "full_chars": 0},
        "capabilities": {
            "api": {"applicable": False},
            "mcp": {"applicable": False},
            "a2a": {"applicable": False},
            "skills": {"applicable": False},
        },
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    root = tmp_path / "repo"
    docs = root / "docs"
    site = root / "site"
    docs.mkdir(parents=True)
    (site / "guide").mkdir(parents=True)
    sources = {
        "docs/index.md": b"# Home\n\nSource home.\n",
        "docs/guide.md": b"# Guide\n\nSource guide.\n",
    }
    for relative, payload in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    (site / "index.html").write_text(
        "<!doctype html><html><head><title>Home</title></head><body>Home</body></html>",
        encoding="utf-8",
    )
    (site / "guide" / "index.html").write_text(
        "<!doctype html><html><head><title>Guide</title></head><body>Guide</body></html>",
        encoding="utf-8",
    )
    readiness = _readiness()
    (root / "docs" / "agent-readiness.schema.json").write_text(
        json.dumps(SCHEMA, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / "docs" / "agent-readiness.json").write_text(
        json.dumps(readiness, sort_keys=True) + "\n", encoding="utf-8"
    )
    entries = [
        {
            "source": relative,
            "url": canonical,
            "canonical_url": canonical,
            "markdown_url": markdown,
            "sha256": _digest(payload),
            "bytes": len(payload),
        }
        for (relative, payload), canonical, markdown in zip(
            sources.items(),
            ("https://docs.example.test/", "https://docs.example.test/guide/"),
            (
                "https://docs.example.test/index.md",
                "https://docs.example.test/guide/index.md",
            ),
        )
    ]
    mirror = {
        "schema_version": pages_readiness.SCHEMA_VERSION,
        "url_contract": pages_readiness.MIRROR_CONTRACT,
        "applicable": True,
        "entries": entries,
    }
    readiness_manifest = {
        "schema_version": pages_readiness.SCHEMA_VERSION,
        "generator_version": "1.0.0",
        "project": readiness["project"],
        "applicability": readiness["applicability"],
        "standards": readiness["standards"],
        "content_signals": readiness["content_signals"],
        "capabilities": readiness["capabilities"],
        "capability_evidence": {},
        "budgets": {
            **readiness["budgets"],
            "full_requested": False,
            "full_effective_chars": 0,
        },
        "generated": [
            "llms.txt",
            "llms-sections/guides/llms.txt",
            "markdown-mirror-manifest.json",
        ],
        "provenance": {
            "pages": [
                {
                    "source": item["source"],
                    "sha256": item["sha256"],
                    "bytes": item["bytes"],
                }
                for item in entries
            ]
        },
    }
    (root / "markdown-mirror-manifest.json").write_text(
        json.dumps(mirror, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / "agent-readiness-manifest.json").write_text(
        json.dumps(readiness_manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / "llms.txt").write_text("# Fixture\n", encoding="utf-8")
    section_index = root / "llms-sections" / "guides" / "llms.txt"
    section_index.parent.mkdir(parents=True)
    section_index.write_text("# Guides\n", encoding="utf-8")
    return root, site, readiness


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_build_publishes_source_markdown_and_served_mime(
    tmp_path: Path,
) -> None:
    root, site, _ = _fixture(tmp_path)

    result = pages_readiness.build(root, site)

    assert result["ok"] is True
    assert (site / "index.md").read_bytes() == (root / "docs/index.md").read_bytes()
    assert (site / "guide/index.md").read_bytes() == (
        root / "docs/guide.md"
    ).read_bytes()
    assert (site / "llms.txt").read_bytes() == (root / "llms.txt").read_bytes()
    assert (site / "llms-sections/guides/llms.txt").read_bytes() == (
        root / "llms-sections/guides/llms.txt"
    ).read_bytes()
    assert result["checker_version"] == pages_readiness.CHECKER_VERSION
    assert result["schema_version"] == pages_readiness.SCHEMA_VERSION
    assert result["mirror_contract"] == pages_readiness.MIRROR_CONTRACT
    assert mimetypes.guess_type("index.md")[0] == "text/markdown"
    index_html = (site / "index.html").read_text(encoding="utf-8")
    assert '<link rel="alternate" type="text/markdown"' in index_html
    assert (
        "<!-- agent-utilities-markdown "
        'alternate="https://docs.example.test/index.md" '
        'llms="https://docs.example.test/llms.txt" -->'
    ) in index_html
    assert "agent-utilities-markdown" not in (site / "index.md").read_text(
        encoding="utf-8"
    )
    assert (site / "robots.txt").read_text(encoding="utf-8") == (
        "Sitemap: https://docs.example.test/sitemap.xml\n"
    )
    assert "<loc>https://docs.example.test/</loc>" in (site / "sitemap.xml").read_text(
        encoding="utf-8"
    )

    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {
            **http.server.SimpleHTTPRequestHandler.extensions_map,
            ".md": "text/markdown",
        }

        def log_message(self, *_args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(site))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/index.md") as response:
            assert response.headers.get_content_type() == "text/markdown"
            assert response.read() == (site / "index.md").read_bytes()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_second_build_and_offline_tck_are_idempotent(tmp_path: Path) -> None:
    root, site, _ = _fixture(tmp_path)

    pages_readiness.build(root, site)
    before = _snapshot(site)
    pages_readiness.build(root, site)
    after = _snapshot(site)
    checked = pages_readiness.build(root, site, check=True)

    assert before == after
    assert (site / "index.html").read_text(encoding="utf-8").count(
        "agent-utilities-markdown"
    ) == 1
    assert checked["ok"] is True


def test_noindex_and_deprecated_html_state_is_preserved_and_not_sitemapped(
    tmp_path: Path,
) -> None:
    root, site, _ = _fixture(tmp_path)
    (site / "guide" / "index.html").write_text(
        '<html><head><meta content="noindex,nofollow" name="robots">'
        '<meta content="deprecated" name="agent-document-state"></head></html>',
        encoding="utf-8",
    )

    pages_readiness.build(root, site)

    guide = (site / "guide" / "index.html").read_text(encoding="utf-8")
    sitemap = (site / "sitemap.xml").read_text(encoding="utf-8")
    assert "noindex,nofollow" in guide
    assert 'content="deprecated"' in guide
    assert "https://docs.example.test/guide/" not in sitemap
    assert "text/markdown" in guide
    assert "agent-utilities-markdown" in guide


def test_conflicting_html_directive_fails_closed(tmp_path: Path) -> None:
    root, site, _ = _fixture(tmp_path)
    index = site / "index.html"
    index.write_text(
        "<html><head><!-- agent-utilities-markdown "
        'alternate="https://docs.example.test/wrong/index.md" '
        'llms="https://docs.example.test/llms.txt" -->'
        "</head></html>",
        encoding="utf-8",
    )

    with pytest.raises(
        pages_readiness.ReadinessTckError, match="html-directive-conflict"
    ):
        pages_readiness.build(root, site)


def test_directive_marker_is_comment_specific(tmp_path: Path) -> None:
    root, site, _ = _fixture(tmp_path / "prose")
    prose = b"# Home\n\nThe agent-utilities-markdown contract is documented here.\n"
    (root / "docs/index.md").write_bytes(prose)
    mirror_path = root / "markdown-mirror-manifest.json"
    mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    mirror["entries"][0]["sha256"] = _digest(prose)
    mirror["entries"][0]["bytes"] = len(prose)
    manifest_path = root / "agent-readiness-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["provenance"]["pages"][0]["sha256"] = _digest(prose)
    manifest["provenance"]["pages"][0]["bytes"] = len(prose)
    mirror_path.write_text(json.dumps(mirror), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    pages_readiness.build(root, site)
    index = site / "index.html"
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "</body>", "agent-utilities-markdown prose</body>"
        ),
        encoding="utf-8",
    )
    pages_readiness.build(root, site)
    assert "agent-utilities-markdown prose" in index.read_text(encoding="utf-8")

    root, site, _ = _fixture(tmp_path / "injected")
    injected = (
        b'# Home\n\n<!-- agent-utilities-markdown alternate="https://docs.example.test/'
        b'index.md" llms="https://docs.example.test/llms.txt" -->\n'
    )
    (root / "docs/index.md").write_bytes(injected)
    mirror_path = root / "markdown-mirror-manifest.json"
    mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    mirror["entries"][0]["sha256"] = _digest(injected)
    mirror["entries"][0]["bytes"] = len(injected)
    manifest_path = root / "agent-readiness-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["provenance"]["pages"][0]["sha256"] = _digest(injected)
    manifest["provenance"]["pages"][0]["bytes"] = len(injected)
    mirror_path.write_text(json.dumps(mirror), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        pages_readiness.ReadinessTckError, match="source-agent-directive"
    ):
        pages_readiness.build(root, site)


def test_robot_policy_is_preserved_and_conflicting_sitemap_rejected(
    tmp_path: Path,
) -> None:
    root, site, _ = _fixture(tmp_path)
    robots = site / "robots.txt"
    robots.write_text(
        "User-agent: ExampleBot\nDisallow: /private\n# operator policy\n",
        encoding="utf-8",
    )

    pages_readiness.build(root, site)
    policy = robots.read_text(encoding="utf-8")
    assert "User-agent: ExampleBot\nDisallow: /private\n# operator policy\n" in policy
    assert policy.count("Sitemap: https://docs.example.test/sitemap.xml\n") == 1
    assert "Allow: /" not in policy
    pages_readiness.build(root, site)
    assert robots.read_text(encoding="utf-8") == policy

    root, site, _ = _fixture(tmp_path / "conflict")
    (site / "robots.txt").write_text(
        "Sitemap: https://other.example.test/sitemap.xml\n", encoding="utf-8"
    )
    with pytest.raises(
        pages_readiness.ReadinessTckError, match="robots-sitemap-conflict"
    ):
        pages_readiness.build(root, site)


def test_stale_source_digest_fails_closed(tmp_path: Path) -> None:
    root, site, _ = _fixture(tmp_path)
    pages_readiness.build(root, site)
    (root / "docs/index.md").write_text("# Changed\n", encoding="utf-8")

    with pytest.raises(pages_readiness.ReadinessTckError, match="source-digest-stale"):
        pages_readiness.build(root, site, check=True)


def test_cli_failure_result_is_versioned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, _, _ = _fixture(tmp_path)
    (root / "docs/index.md").write_text("# Changed\n", encoding="utf-8")

    assert pages_readiness.main(["check", "--root", str(root), "--site", "site"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["checker_version"] == pages_readiness.CHECKER_VERSION
    assert result["schema_version"] == pages_readiness.SCHEMA_VERSION
    assert result["mirror_contract"] == pages_readiness.MIRROR_CONTRACT
    assert result["error_code"] == "source-digest-stale"


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("http://docs.example.test/api", "api-endpoint-url-invalid"),
        ("https://127.0.0.1/api", "api-endpoint-private-url"),
    ],
)
def test_malformed_or_private_capability_reference_is_rejected(
    tmp_path: Path,
    endpoint: str,
    expected: str,
) -> None:
    root, site, readiness = _fixture(tmp_path)
    readiness["capabilities"]["api"] = {
        "applicable": True,
        "artifact": "api-capability.json",
        "endpoint": endpoint,
    }
    (root / "api-capability.json").write_text(
        json.dumps({"applicable": True, "surface": "api", "source": "docs/index.md"}),
        encoding="utf-8",
    )
    (root / "docs/agent-readiness.json").write_text(
        json.dumps(readiness, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(pages_readiness.ReadinessTckError, match=expected):
        pages_readiness.build(root, site)


def test_traversal_symlink_and_oversized_outputs_fail_closed(tmp_path: Path) -> None:
    root, site, _ = _fixture(tmp_path)
    mirror_path = root / "markdown-mirror-manifest.json"
    mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    mirror["entries"][0]["markdown_url"] = "https://docs.example.test/../index.md"
    mirror_path.write_text(json.dumps(mirror), encoding="utf-8")
    with pytest.raises(
        pages_readiness.ReadinessTckError, match="markdown-path-invalid"
    ):
        pages_readiness.build(root, site)

    mirror["entries"][0]["markdown_url"] = "https://docs.example.test/index.md"
    mirror_path.write_text(json.dumps(mirror), encoding="utf-8")
    (root / "llms.txt").write_bytes(
        b"x" * (pages_readiness.MAX_GENERATED_FILE_BYTES + 1)
    )
    with pytest.raises(
        pages_readiness.ReadinessTckError, match="generated-output-oversize"
    ):
        pages_readiness.build(root, site)


def test_source_recursion_and_symlink_fail_closed(tmp_path: Path) -> None:
    root, site, _ = _fixture(tmp_path)
    mirror_path = root / "markdown-mirror-manifest.json"
    mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    entry = mirror["entries"][0]
    entry["source"] = "site/index.html"
    entry["sha256"] = _digest((site / "index.html").read_bytes())
    entry["bytes"] = (site / "index.html").stat().st_size
    readiness_manifest_path = root / "agent-readiness-manifest.json"
    readiness_manifest = json.loads(readiness_manifest_path.read_text(encoding="utf-8"))
    readiness_manifest["provenance"]["pages"][0] = {
        "source": entry["source"],
        "sha256": entry["sha256"],
        "bytes": entry["bytes"],
    }
    mirror_path.write_text(json.dumps(mirror), encoding="utf-8")
    readiness_manifest_path.write_text(json.dumps(readiness_manifest), encoding="utf-8")
    with pytest.raises(
        pages_readiness.ReadinessTckError, match="source-site-recursion"
    ):
        pages_readiness.build(root, site)

    mirror["entries"][0]["source"] = "docs/alias.md"
    mirror["entries"][0]["sha256"] = _digest((root / "docs/index.md").read_bytes())
    mirror["entries"][0]["bytes"] = (root / "docs/index.md").stat().st_size
    readiness_manifest["provenance"]["pages"][0] = {
        "source": "docs/alias.md",
        "sha256": mirror["entries"][0]["sha256"],
        "bytes": mirror["entries"][0]["bytes"],
    }
    (root / "docs/alias.md").symlink_to(root / "docs/index.md")
    mirror_path.write_text(json.dumps(mirror), encoding="utf-8")
    readiness_manifest_path.write_text(json.dumps(readiness_manifest), encoding="utf-8")
    with pytest.raises(pages_readiness.ReadinessTckError, match="source-symlink"):
        pages_readiness.build(root, site)


def test_source_markdown_secret_is_not_published(tmp_path: Path) -> None:
    root, site, _ = _fixture(tmp_path)
    source = root / "docs/index.md"
    payload = b"# Home\n\napi_key = super-secret-value-123\n"
    source.write_bytes(payload)
    mirror_path = root / "markdown-mirror-manifest.json"
    mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    mirror["entries"][0]["sha256"] = _digest(payload)
    mirror["entries"][0]["bytes"] = len(payload)
    readiness_manifest_path = root / "agent-readiness-manifest.json"
    readiness_manifest = json.loads(readiness_manifest_path.read_text(encoding="utf-8"))
    readiness_manifest["provenance"]["pages"][0]["sha256"] = _digest(payload)
    readiness_manifest["provenance"]["pages"][0]["bytes"] = len(payload)
    mirror_path.write_text(json.dumps(mirror), encoding="utf-8")
    readiness_manifest_path.write_text(json.dumps(readiness_manifest), encoding="utf-8")

    with pytest.raises(
        pages_readiness.ReadinessTckError, match="source-secret-like-value"
    ):
        pages_readiness.build(root, site)
