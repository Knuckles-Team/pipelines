"""Focused acceptance tests for PIPE-PAGES-R020.1 through R020.5."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.docs import claims
from pipelines_hooks.docs.claims import DocClaim, claim_findings, parse_claims
from pipelines_hooks.docs.public_surface import validate
from tests.hooks.conftest import Repo


def _claim_root(root: Path) -> int:
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "bootstrap.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\n[project.scripts]\nfixture = 'pkg:main'\n", encoding="utf-8"
    )
    (root / "registry.json").write_text(json.dumps({"nodes": [{"name": "docs"}]}), encoding="utf-8")
    return sum(1 for path in root.rglob("*") if path.is_file())


# spec: PIPE-PAGES-R020.1
def test_doc_claim_kind_is_closed() -> None:
    with pytest.raises(ValueError, match="unsupported documentation claim kind"):
        DocClaim(file="README.md", line=3, kind="url", text="https://example.invalid")


# spec: PIPE-PAGES-R020.2
def test_resolvers_check_each_kind(tmp_path: Path) -> None:
    expected_files = _claim_root(tmp_path)
    good = [
        DocClaim("README.md", 1, "path", "docs/guide.md"),
        DocClaim("README.md", 2, "command", "scripts/bootstrap.sh"),
        DocClaim("README.md", 3, "gate", "public-surface"),
        DocClaim("README.md", 4, "count", f"files={expected_files}"),
        DocClaim("README.md", 5, "diagram-node", "docs"),
    ]
    assert claim_findings(tmp_path, good) == []

    bad = [
        DocClaim("README.md", 6, "path", "docs/missing.md"),
        DocClaim("README.md", 7, "command", "scripts/missing.sh"),
        DocClaim("README.md", 8, "gate", "missing-gate"),
        DocClaim("README.md", 9, "count", "files=999"),
        DocClaim("README.md", 10, "diagram-node", "missing-node"),
    ]
    findings = claim_findings(tmp_path, bad)
    assert len(findings) == len(bad)
    assert all("README.md:" in finding for finding in findings)


# spec: PIPE-PAGES-R020.3
def test_validate_calls_claim_findings(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    repo.commit(
        {
            "README.md": "# fixture\n\n<!-- claim:path docs/missing.md -->\n\n## Install\n\n```bash\nuv sync\n```\n",
        },
        "docs",
    )
    called: list[list[DocClaim]] = []

    def fake_claim_findings(root: Path, source_claims: list[DocClaim]) -> list[str]:
        called.append(source_claims)
        return ["README.md:3 path docs/missing.md"]

    monkeypatch.setattr("pipelines_hooks.docs.public_surface.claim_findings", fake_claim_findings)
    findings = validate(repo.root)
    assert findings[-1] == "README.md:3 path docs/missing.md"
    assert [claim.kind for claim in called[0]] == ["path"]


# spec: PIPE-PAGES-R020.4
def test_unresolvable_claim_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _claim_root(tmp_path)
    monkeypatch.delitem(claims.RESOLVERS, "path")
    findings = claim_findings(tmp_path, [DocClaim("README.md", 4, "path", "docs/guide.md")])
    assert findings == ["README.md:4 claims-unchecked path docs/guide.md"]


# spec: PIPE-PAGES-R020.5
def test_claims_summary_line(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit(
        {
            "README.md": (
                "# fixture\n\n"
                "<!-- claim:path pyproject.toml -->\n"
                "<!-- claim:path docs/missing.md -->\n\n"
                "## Install\n\n```bash\nuv sync\n```\n"
            )
        },
        "docs",
    )
    assert repo.run("public-surface") == 1
    output = capsys.readouterr().out
    assert "claims: checked 2, unresolved 1" in output
    assert "README.md:4 path docs/missing.md" in output


def test_parser_preserves_source_lines() -> None:
    claims_found = parse_claims("# title\n\n<!-- claim:gate public-surface -->\n", file="README.md")
    assert claims_found == [DocClaim("README.md", 3, "gate", "public-surface")]
