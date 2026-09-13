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


def _fixture(
    tmp_path: Path, base: str = "https://docs.example.test/"
) -> tuple[Path, Path, dict[str, Any]]:
    """A flat ``mkdocs build --site-dir site`` tree for a site rooted at ``base``.

    ``base`` is the mkdocs ``site_url``; the HTML is always written at the
    built site's root (``site/index.html``, ``site/guide/index.html``) exactly
    as mkdocs does, whatever path prefix ``base`` carries.
    """

    root = tmp_path / "repo"
    docs = root / "docs"
    site = root / "site"
    docs.mkdir(parents=True)
    (root / "pages").mkdir(parents=True)
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
    (root / "mkdocs.yml").write_text(
        f"site_name: Fixture\nsite_url: {base}\n", encoding="utf-8"
    )
    readiness = _readiness()
    (root / "pages" / "agent-readiness.schema.json").write_text(
        json.dumps(SCHEMA, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / "pages" / "agent-readiness.json").write_text(
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
            (base, f"{base}guide/"),
            (f"{base}index.md", f"{base}guide/index.md"),
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
    readiness["project"]["kind"] = "package"
    readiness["capabilities"]["api"] = {
        "applicable": True,
        "artifact": "api-capability.json",
        "endpoint": endpoint,
    }
    (root / "api-capability.json").write_text(
        json.dumps({"applicable": True, "surface": "api", "source": "docs/index.md"}),
        encoding="utf-8",
    )
    (root / "pages/agent-readiness.json").write_text(
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


def test_omitted_readiness_paths_default_to_the_pages_layout(tmp_path: Path) -> None:
    """No explicit readiness_input/schema resolves under the new pages/ layout."""

    root, site, _ = _fixture(tmp_path)

    result = pages_readiness.build(root, site)

    assert result["ok"] is True
    assert (root / "pages" / "agent-readiness.json").is_file()


def test_content_source_declares_a_legacy_docs_layout_explicitly(
    tmp_path: Path,
) -> None:
    """A repository still on docs/ must declare content_source explicitly.

    There is no fallback probing between layouts: moving the readiness
    artifacts to docs/ without also declaring content_source="docs" fails
    closed exactly like any other missing input, rather than silently
    falling back to check docs/ after pages/ comes up empty.
    """

    root, site, _ = _fixture(tmp_path)
    (root / "pages" / "agent-readiness.json").rename(
        root / "docs" / "agent-readiness.json"
    )
    (root / "pages" / "agent-readiness.schema.json").rename(
        root / "docs" / "agent-readiness.schema.json"
    )

    with pytest.raises(pages_readiness.ReadinessTckError, match="readiness-input-"):
        pages_readiness.build(root, site)

    result = pages_readiness.build(root, site, content_source="docs")
    assert result["ok"] is True


def test_mkdocs_docs_dir_tolerates_the_real_fleet_pymdownx_tag(tmp_path: Path) -> None:
    """`!!python/name:` never reaches a constructor.

    `mkdocs_docs_dir` reads via `yaml.compose`, which runs only the
    parser/composer stage -- it never calls a constructor, so this tag
    (copied verbatim from a real connector's `mkdocs.yml`) stays an inert
    `ScalarNode` and cannot execute anything. No `docs_dir` key is declared,
    so the result is `None` (mkdocs's own "docs" default applies upstream).
    """

    (tmp_path / "mkdocs.yml").write_text(
        "site_name: Fixture\n"
        "markdown_extensions:\n"
        "  - pymdownx.highlight:\n"
        "      anchor_linenums: true\n"
        "  - pymdownx.superfences:\n"
        "      custom_fences:\n"
        "        - name: mermaid\n"
        "          class: mermaid\n"
        "          format: !!python/name:pymdownx.superfences.fence_code_format\n",
        encoding="utf-8",
    )

    assert pages_readiness.mkdocs_docs_dir(tmp_path) is None


def test_mkdocs_docs_dir_missing_key_is_none(tmp_path: Path) -> None:
    (tmp_path / "mkdocs.yml").write_text(
        "site_name: Fixture\nnav:\n  - Home: index.md\n", encoding="utf-8"
    )

    assert pages_readiness.mkdocs_docs_dir(tmp_path) is None


def test_mkdocs_docs_dir_declared_scalar(tmp_path: Path) -> None:
    (tmp_path / "mkdocs.yml").write_text(
        "site_name: Fixture\ndocs_dir: pages\n", encoding="utf-8"
    )

    assert pages_readiness.mkdocs_docs_dir(tmp_path) == "pages"


def test_mkdocs_docs_dir_non_scalar_fails_loudly(tmp_path: Path) -> None:
    """A `docs_dir` that isn't a plain string is a named error, not a guess."""

    (tmp_path / "mkdocs.yml").write_text(
        "site_name: Fixture\ndocs_dir:\n  - pages\n  - docs\n", encoding="utf-8"
    )

    with pytest.raises(
        pages_readiness.ReadinessTckError, match="content-source-docs-dir-invalid"
    ):
        pages_readiness.mkdocs_docs_dir(tmp_path)


def test_validate_content_source_requires_a_declared_value(tmp_path: Path) -> None:
    with pytest.raises(
        pages_readiness.ReadinessTckError, match="content-source-required"
    ):
        pages_readiness.validate_content_source(tmp_path, "")


def test_validate_content_source_missing_directory_fails_loudly(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        pages_readiness.ReadinessTckError, match="content-source-containment"
    ):
        pages_readiness.validate_content_source(tmp_path, "pages")


def test_validate_content_source_mismatched_docs_dir_fails_loudly(
    tmp_path: Path,
) -> None:
    (tmp_path / "pages").mkdir()
    (tmp_path / "mkdocs.yml").write_text(
        "site_name: Fixture\ndocs_dir: docs\n", encoding="utf-8"
    )

    with pytest.raises(
        pages_readiness.ReadinessTckError, match="content-source-mismatch"
    ):
        pages_readiness.validate_content_source(tmp_path, "pages")


def test_validate_content_source_matching_docs_dir_and_real_fleet_tag_passes(
    tmp_path: Path,
) -> None:
    (tmp_path / "pages").mkdir()
    (tmp_path / "mkdocs.yml").write_text(
        "site_name: Fixture\n"
        "docs_dir: pages\n"
        "markdown_extensions:\n"
        "  - pymdownx.superfences:\n"
        "      custom_fences:\n"
        "        - name: mermaid\n"
        "          class: mermaid\n"
        "          format: !!python/name:pymdownx.superfences.fence_code_format\n",
        encoding="utf-8",
    )

    result = pages_readiness.validate_content_source(tmp_path, "pages")
    assert result == {
        "ok": True,
        "content_source": "pages",
        "mkdocs_docs_dir": "pages",
    }


def test_validate_content_source_no_mkdocs_yml_is_not_a_mismatch(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()

    result = pages_readiness.validate_content_source(tmp_path, "docs")
    assert result == {
        "ok": True,
        "content_source": "docs",
        "mkdocs_docs_dir": None,
    }


def test_cli_validate_content_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pages").mkdir()

    assert (
        pages_readiness.main(
            [
                "validate-content-source",
                "--root",
                str(tmp_path),
                "--content-source",
                "pages",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "ok": True,
        "content_source": "pages",
        "mkdocs_docs_dir": None,
    }

    assert (
        pages_readiness.main(
            [
                "validate-content-source",
                "--root",
                str(tmp_path),
                "--content-source",
                "docs",
            ]
        )
        == 1
    )
    failure = json.loads(capsys.readouterr().out)
    assert failure["ok"] is False
    assert failure["error_code"] == "content-source-containment"


PROJECT_SITE = "https://example.github.io/example-connector/"
ROOT_SITE = "https://example.github.io/"
CUSTOM_DOMAIN = "https://docs.example.com/"


@pytest.mark.parametrize(
    ("url", "site_url", "kind", "expected"),
    [
        # Project page: the /<repository>/ prefix exists only at serve time.
        (PROJECT_SITE, PROJECT_SITE, "html", "index.html"),
        (
            f"{PROJECT_SITE}installation/",
            PROJECT_SITE,
            "html",
            "installation/index.html",
        ),
        (
            f"{PROJECT_SITE}guides/setup/",
            PROJECT_SITE,
            "html",
            "guides/setup/index.html",
        ),
        (
            f"{PROJECT_SITE}installation/index.md",
            PROJECT_SITE,
            "markdown",
            "installation/index.md",
        ),
        # Root user/org page and custom domain: the base path is "/".
        (ROOT_SITE, ROOT_SITE, "html", "index.html"),
        (f"{ROOT_SITE}guide/", ROOT_SITE, "html", "guide/index.html"),
        (f"{ROOT_SITE}index.md", ROOT_SITE, "markdown", "index.md"),
        (
            f"{CUSTOM_DOMAIN}reference/api/",
            CUSTOM_DOMAIN,
            "html",
            "reference/api/index.html",
        ),
        # use_directory_urls: false pages are served from their .html file.
        (f"{PROJECT_SITE}installation.html", PROJECT_SITE, "html", "installation.html"),
        (f"{PROJECT_SITE}guides/index.html", PROJECT_SITE, "html", "guides/index.html"),
        (f"{PROJECT_SITE}installation", PROJECT_SITE, "html", "installation.html"),
    ],
)
def test_site_output_path_strips_the_site_url_base(
    url: str, site_url: str, kind: str, expected: str
) -> None:
    assert pages_readiness.site_output_path(url, site_url, kind=kind) == expected


@pytest.mark.parametrize(
    ("url", "site_url", "kind", "expected"),
    [
        (
            "https://other.example.com/guide/",
            PROJECT_SITE,
            "html",
            "mirror-origin-mismatch",
        ),
        (
            f"{ROOT_SITE}other-repository/guide/",
            PROJECT_SITE,
            "html",
            "canonical-outside-site",
        ),
        (f"{ROOT_SITE}index.md", PROJECT_SITE, "markdown", "markdown-outside-site"),
        (f"{PROJECT_SITE}guide/", PROJECT_SITE.rstrip("/"), "html", "site-url-invalid"),
        (f"{PROJECT_SITE}guide.md", PROJECT_SITE, "html", "canonical-path-invalid"),
        (
            f"{PROJECT_SITE}guide/",
            PROJECT_SITE,
            "markdown",
            "markdown-fallback-invalid",
        ),
    ],
)
def test_site_output_path_rejects_urls_outside_the_declared_site(
    url: str, site_url: str, kind: str, expected: str
) -> None:
    with pytest.raises(pages_readiness.ReadinessTckError, match=expected):
        pages_readiness.site_output_path(url, site_url, kind=kind)


def test_project_page_site_built_flat_passes_build_and_tck(tmp_path: Path) -> None:
    """``mkdocs build --site-dir site`` output for a project page, unnested."""

    root, site, _ = _fixture(tmp_path, PROJECT_SITE)

    assert pages_readiness.build(root, site)["ok"] is True
    assert pages_readiness.build(root, site, check=True)["ok"] is True

    assert (site / "index.md").read_bytes() == (root / "docs/index.md").read_bytes()
    assert (site / "guide/index.md").read_bytes() == (
        root / "docs/guide.md"
    ).read_bytes()
    assert not (site / "example-connector").exists()
    assert (
        "<!-- agent-utilities-markdown "
        f'alternate="{PROJECT_SITE}guide/index.md" llms="{PROJECT_SITE}llms.txt" -->'
    ) in (site / "guide/index.html").read_text(encoding="utf-8")
    assert (site / "robots.txt").read_text(encoding="utf-8") == (
        f"Sitemap: {PROJECT_SITE}sitemap.xml\n"
    )
    assert f"<loc>{PROJECT_SITE}guide/</loc>" in (site / "sitemap.xml").read_text(
        encoding="utf-8"
    )


def test_use_directory_urls_false_site_passes_build_and_tck(tmp_path: Path) -> None:
    root, site, _ = _fixture(tmp_path, PROJECT_SITE)
    (site / "guide" / "index.html").rename(site / "guide.html")
    (site / "guide").rmdir()
    mirror_path = root / "markdown-mirror-manifest.json"
    mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    mirror["entries"][0]["url"] = mirror["entries"][0]["canonical_url"] = (
        f"{PROJECT_SITE}index.html"
    )
    mirror["entries"][1]["url"] = mirror["entries"][1]["canonical_url"] = (
        f"{PROJECT_SITE}guide.html"
    )
    mirror_path.write_text(json.dumps(mirror), encoding="utf-8")

    assert pages_readiness.build(root, site)["ok"] is True
    assert pages_readiness.build(root, site, check=True)["ok"] is True
    assert "text/markdown" in (site / "guide.html").read_text(encoding="utf-8")
    assert (site / "guide/index.md").read_bytes() == (
        root / "docs/guide.md"
    ).read_bytes()


def test_missing_site_url_fails_closed(tmp_path: Path) -> None:
    root, site, _ = _fixture(tmp_path)
    (root / "mkdocs.yml").write_text("site_name: Fixture\n", encoding="utf-8")

    with pytest.raises(pages_readiness.ReadinessTckError, match="site-url-required"):
        pages_readiness.build(root, site)


def _declare(
    root: Path,
    readiness: dict[str, Any],
    manifest_capabilities: dict[str, Any],
    *,
    discovery: tuple[str, ...] = (),
) -> None:
    """Write a readiness declaration and the manifest the generator emits for it."""

    (root / "pages/agent-readiness.json").write_text(
        json.dumps(readiness, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_path = root / "agent-readiness-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["project"] = readiness["project"]
    manifest["applicability"] = readiness["applicability"]
    manifest["capabilities"] = manifest_capabilities
    manifest["generated"] = [
        "llms.txt",
        "llms-sections/guides/llms.txt",
        "markdown-mirror-manifest.json",
        *discovery,
    ]
    for relative in discovery:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text('{"schema_version": "fixture"}\n', encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def _connector(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    """A package with a real skill directory and an MCP capability authority."""

    root, site, readiness = _fixture(tmp_path, PROJECT_SITE)
    readiness["project"]["kind"] = "package"
    readiness["applicability"]["capabilities"] = True
    skill = root / "skills" / "example-connector-reader" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: example-connector-reader\n---\n# Reader\n", encoding="utf-8"
    )
    (root / "example_connector").mkdir()
    (root / "example_connector" / "mcp_server.py").write_text(
        "SERVER = 1\n", encoding="utf-8"
    )
    (root / "mcp-capability.json").write_text(
        json.dumps(
            {
                "applicable": True,
                "surface": "mcp",
                "version": "capability/v1",
                "source": "example_connector/mcp_server.py",
            }
        ),
        encoding="utf-8",
    )
    return root, site, readiness


STDIO_MCP = {
    "applicable": True,
    "artifact": "mcp-capability.json",
    "transport": "stdio",
    "reachability": "local",
}


def test_stdio_mcp_and_skills_connector_passes_build_and_tck(tmp_path: Path) -> None:
    root, site, readiness = _connector(tmp_path)
    readiness["capabilities"]["mcp"] = dict(STDIO_MCP)
    readiness["capabilities"]["skills"] = {"applicable": True, "path": "skills"}
    _declare(
        root,
        readiness,
        {
            "api": {"applicable": False},
            "mcp": dict(STDIO_MCP),
            "a2a": {"applicable": False},
            "skills": {"applicable": True, "path": "skills"},
        },
        discovery=(".well-known/agent-skills.json",),
    )

    assert pages_readiness.build(root, site)["ok"] is True
    assert pages_readiness.build(root, site, check=True)["ok"] is True
    assert (site / ".well-known/agent-skills.json").read_bytes() == (
        root / ".well-known/agent-skills.json"
    ).read_bytes()


def test_in_cluster_http_mcp_surface_requires_artifact_proof(tmp_path: Path) -> None:
    root, site, readiness = _connector(tmp_path)
    declared = {
        "applicable": True,
        "artifact": "mcp-capability.json",
        "transport": "streamable-http",
        "reachability": "in-cluster",
        "service_identity": "example-connector.connectors",
    }
    readiness["capabilities"]["mcp"] = declared
    manifest_mcp = {
        "applicable": True,
        "artifact": "mcp-capability.json",
        "transport": "streamable-http",
        "reachability": "in-cluster",
    }
    _declare(
        root,
        readiness,
        {
            "api": {"applicable": False},
            "mcp": manifest_mcp,
            "a2a": {"applicable": False},
            "skills": {"applicable": False},
        },
    )
    with pytest.raises(
        pages_readiness.ReadinessTckError, match="mcp-transport-not-proven"
    ):
        pages_readiness.build(root, site)

    artifact = json.loads((root / "mcp-capability.json").read_text(encoding="utf-8"))
    artifact["http_transport"] = True
    (root / "mcp-capability.json").write_text(json.dumps(artifact), encoding="utf-8")
    assert pages_readiness.build(root, site)["ok"] is True


def test_legacy_public_endpoint_declaration_is_not_reported_stale(
    tmp_path: Path,
) -> None:
    """The generator omits ``endpoint``/OAuth references from its manifest."""

    root, site, readiness = _connector(tmp_path)
    oauth = root / ".well-known" / "oauth-protected-resource"
    oauth.parent.mkdir(parents=True)
    oauth.write_text('{"resource": "https://mcp.example.com"}\n', encoding="utf-8")
    readiness["capabilities"]["mcp"] = {
        "applicable": True,
        "artifact": "mcp-capability.json",
        "endpoint": "https://mcp.example.com/mcp",
        "oauth_protected_resource": ".well-known/oauth-protected-resource",
    }
    _declare(
        root,
        readiness,
        {
            "api": {"applicable": False},
            "mcp": {"applicable": True, "artifact": "mcp-capability.json"},
            "a2a": {"applicable": False},
            "skills": {"applicable": False},
        },
        discovery=(".well-known/api-catalog",),
    )

    assert pages_readiness.build(root, site)["ok"] is True


@pytest.mark.parametrize(
    ("surface", "declared", "expected"),
    [
        (
            "mcp",
            {"endpoint": "https://mcp.example.com/mcp"},
            "capability-reachability-inconsistent",
        ),
        (
            "mcp",
            {"service_identity": "example-connector.connectors"},
            "capability-reachability-inconsistent",
        ),
        (
            "mcp",
            {
                "reachability": "in-cluster",
                "service_identity": "example-connector.connectors",
            },
            "capability-reachability-inconsistent",
        ),
        (
            "mcp",
            {"transport": "streamable-http"},
            "capability-reachability-inconsistent",
        ),
        (
            "mcp",
            {"transport": "streamable-http", "reachability": "public"},
            "capability-endpoint-required",
        ),
        (
            "mcp",
            {
                "transport": "streamable-http",
                "reachability": "public",
                "endpoint": "https://mcp.example.com/mcp",
                "service_identity": "example-connector.connectors",
            },
            "capability-reachability-inconsistent",
        ),
        (
            "mcp",
            {"transport": "streamable-http", "reachability": "in-cluster"},
            "capability-service-identity-required",
        ),
        (
            "mcp",
            {
                "transport": "streamable-http",
                "reachability": "in-cluster",
                "service_identity": "example-connector.connectors",
                "endpoint": "https://mcp.example.com/mcp",
            },
            "capability-reachability-inconsistent",
        ),
        (
            "mcp",
            {
                "transport": "sse",
                "reachability": "in-cluster",
                "service_identity": "example-connector",
            },
            "capability-service-identity-invalid",
        ),
        (
            "mcp",
            {
                "transport": "sse",
                "reachability": "in-cluster",
                "service_identity": "https://example-connector.connectors",
            },
            "capability-service-identity-invalid",
        ),
        (
            "mcp",
            {
                "transport": "streamable-http",
                "reachability": "public",
                "endpoint": "http://mcp.example.com/mcp",
            },
            "mcp-endpoint-url-invalid",
        ),
        (
            "mcp",
            {
                "transport": "websocket",
                "reachability": "public",
                "endpoint": "https://mcp.example.com/mcp",
            },
            "capability-transport-unsupported",
        ),
        (
            "mcp",
            {"transport": "stdio", "reachability": "nearby"},
            "capability-reachability-invalid",
        ),
        ("mcp", {"reachability": None}, "capability-transport-incomplete"),
        ("a2a", {"surface_override": True}, "capability-transport-unsupported"),
        ("api", {"surface_override": True}, "capability-entry-invalid"),
    ],
)
def test_inconsistent_surface_reachability_is_rejected(
    tmp_path: Path, surface: str, declared: dict[str, Any], expected: str
) -> None:
    root, site, readiness = _connector(tmp_path)
    entry: dict[str, Any] = {**STDIO_MCP, "artifact": f"{surface}-capability.json"}
    overrides = {
        key: value for key, value in declared.items() if key != "surface_override"
    }
    entry.update(overrides)
    entry = {key: value for key, value in entry.items() if value is not None}
    readiness["capabilities"][surface] = entry
    (root / "pages/agent-readiness.json").write_text(
        json.dumps(readiness, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(pages_readiness.ReadinessTckError, match=expected):
        pages_readiness.build(root, site)


@pytest.mark.parametrize(
    ("discovery", "skills_applicable", "expected"),
    [
        ((".well-known/other.json",), False, "generated-path-outside-contract"),
        (
            (".well-known/agent-skills.json/extra",),
            False,
            "generated-path-outside-contract",
        ),
        ((".well-known/agent-skills.json",), False, "generated-discovery-unbound"),
        ((), True, "generated-discovery-unbound"),
        (
            (".well-known/agent-skills.json", ".well-known/mcp-server-card.json"),
            True,
            "generated-discovery-unbound",
        ),
        (
            (".well-known/agent-skills.json", ".well-known/api-catalog"),
            True,
            "generated-discovery-unbound",
        ),
    ],
)
def test_discovery_outputs_are_bound_to_the_declaration(
    tmp_path: Path,
    discovery: tuple[str, ...],
    skills_applicable: bool,
    expected: str,
) -> None:
    root, site, readiness = _connector(tmp_path)
    skills: dict[str, Any] = (
        {"applicable": True, "path": "skills"}
        if skills_applicable
        else {"applicable": False}
    )
    readiness["capabilities"]["mcp"] = dict(STDIO_MCP)
    readiness["capabilities"]["skills"] = skills
    manifest_path = root / "agent-readiness-manifest.json"
    _declare(
        root,
        readiness,
        {
            "api": {"applicable": False},
            "mcp": dict(STDIO_MCP),
            "a2a": {"applicable": False},
            "skills": skills,
        },
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["generated"].extend(discovery)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    for relative in discovery:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.parent.is_file():
            path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(pages_readiness.ReadinessTckError, match=expected):
        pages_readiness.build(root, site)
