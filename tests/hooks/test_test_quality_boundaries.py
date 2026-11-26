"""PIPE-PAGES-R021.7-.12: declared boundaries, runtime reachability and handoff proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.code import boundaries
from pipelines_hooks.code.import_graph import build_runtime_edges
from pipelines_hooks.code.test_quality import RULES, TestQualityFinding
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import Repo

DECLARATION = """version = 1
roots = ["pkg"]
entry_modules = ["pkg.cli"]
receipts = "handoff-receipts.json"

[[components]]
name = "cli"
modules = ["pkg.cli", "pkg"]
[[components]]
name = "core"
modules = ["pkg.core"]
[[components]]
name = "store"
modules = ["pkg.store"]

[[edges]]
from = "cli"
to = "core"
kinds = ["eager-runtime"]
[[edges]]
from = "core"
to = "store"
kinds = ["deferred-runtime"]

[[handoffs]]
id = "core-store"
components = ["core", "store"]
property_test = "tests/test_core.py::test_property"
integration_test = "tests/test_core.py::test_integration"
"""
FILES = {
    "pkg/__init__.py": "",
    "pkg/cli.py": "from pkg import core\n\n\ndef main():\n    return core.run()\n",
    "pkg/core.py": (
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from pkg import orphan\n\n\n"
        "def run():\n    return 1\n\n\n"
        "async def arun():\n    from pkg import store\n\n    return store\n"
    ),
    "pkg/store.py": "VALUE = 1\n",
    "pkg/orphan.py": "VALUE = 2\n",
    ".pipelines/components.toml": DECLARATION,
    "coverage.json": json.dumps({"totals": {"percent_covered": 95}}),
}


def receipts(repo: Repo, **over: object) -> str:
    head = repo.git("rev-parse", "HEAD").strip()
    base = {
        "commit": head,
        "receipts": [
            {"test_id": "tests/test_core.py::test_property", "kind": "property", "outcome": "passed", "seed": 7},
            {
                "test_id": "tests/test_core.py::test_integration",
                "kind": "integration",
                "outcome": "passed",
                "components": ["core", "store"],
            },
        ],
    }
    base.update(over)
    return json.dumps(base)


def build(tmp_path: Path, files: dict[str, str] | None = None) -> Repo:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    repo.commit({**FILES, **(files or {})})
    refresh(repo)
    return repo


def refresh(repo: Repo, **over: object) -> None:
    """Receipts are produced by the test run, outside the commit they describe."""
    repo.write("handoff-receipts.json", receipts(repo, **over))


# spec: PIPE-PAGES-R021.7
def test_model_extends_rules_and_types_edges(tmp_path: Path) -> None:
    assert {"interface-violation", "missing-property-proof", "missing-integration-proof", "orphan-module"} <= set(RULES)
    assert TestQualityFinding("a.py", 3, "orphan-module", "pkg.x").render() == "a.py:3 orphan-module -- pkg.x"
    build(tmp_path)
    modules, edges, dynamic = build_runtime_edges([tmp_path / "pkg"], root=tmp_path)
    kinds = {(e.source, e.target, e.kind, e.line) for e in edges}
    assert ("pkg.core", "pkg.orphan", "type-only", 4) in kinds
    assert ("pkg.core", "pkg.store", "deferred-runtime", 12) in kinds
    assert ("pkg.cli", "pkg.core", "eager-runtime", 1) in kinds and not dynamic and "pkg.store" in modules


# spec: PIPE-PAGES-R021.8
def test_lazy_edges_pass_and_forbidden_or_orphan_fail(tmp_path: Path) -> None:
    repo = build(tmp_path)
    result = boundaries.check(tmp_path, tmp_path / ".pipelines/components.toml")
    rules = sorted((f.rule, f.path, f.line) for f in result.findings)
    assert ("interface-violation", "pkg/core.py", 4) in rules
    assert not [f for f in result.findings if f.detail == "pkg.store"]
    assert [f.detail for f in result.findings if f.rule == "orphan-module"] == ["pkg.orphan"]
    repo.commit({"pkg/cli.py": "from pkg import core\n\n\ndef main():\n    from pkg import store\n    return store\n"})
    refresh(repo)
    forbidden = boundaries.check(tmp_path, tmp_path / ".pipelines/components.toml")
    assert ("pkg/cli.py", 5, "interface-violation") in {(f.path, f.line, f.rule) for f in forbidden.findings}


# spec: PIPE-PAGES-R021.9
def test_wiring_runs_through_the_test_quality_gate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    assert repo.run("test-quality") == 1
    out = capsys.readouterr().out
    assert "orphan-module -- pkg.orphan" in out and "interface-violation -- pkg.core -> pkg.orphan (type-only)" in out
    evidence = tmp_path / "evidence.json"
    repo.run("test-quality", "--evidence", str(evidence))
    assert "boundaries" in json.loads(evidence.read_text())


# spec: PIPE-PAGES-R021.10
def test_refusals_are_cannot_run(tmp_path: Path) -> None:
    repo = build(tmp_path)
    repo.commit({".pipelines/components.toml": "version = 2\n"})
    assert repo.run("test-quality") == 2
    repo.commit(
        {
            ".pipelines/components.toml": DECLARATION,
            "pkg/store.py": "import importlib\n\nm = importlib.import_module(NAME)\n",
        }
    )
    with pytest.raises(CannotRun, match=r"pkg/store.py:3"):
        boundaries.check(tmp_path, tmp_path / ".pipelines/components.toml")
    repo.commit({"pkg/store.py": "VALUE = 1\n"})
    assert repo.run("test-quality") == 2  # receipts describe the previous commit: stale
    skipped = {"commit": "x", "receipts": [{"test_id": "tests/test_core.py::test_property", "outcome": "skipped"}]}
    repo.write("handoff-receipts.json", json.dumps(skipped))
    assert repo.run("test-quality") == 2


# spec: PIPE-PAGES-R021.11
def test_evidence_binds_digests_edges_and_receipts(tmp_path: Path) -> None:
    build(tmp_path)
    ev = boundaries.check(tmp_path, tmp_path / ".pipelines/components.toml").evidence
    assert len(str(ev["declaration_digest"])) == 64 and len(str(ev["source_digest"])) == 64
    assert ["pkg.core", "pkg.store", "pkg/core.py:12", "deferred-runtime"] in ev["edges"]  # type: ignore[operator]
    assert "pkg.orphan" in ev["type_only_excluded"] and "pkg.orphan" not in ev["reachable"]  # type: ignore[operator]
    assert {r["kind"] for r in ev["receipts"]} == {"property", "integration"}  # type: ignore[attr-defined,union-attr]


# spec: PIPE-PAGES-R021.12
def test_hot_path_missing_proofs_and_clean_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    fixed = {
        "pkg/core.py": FILES["pkg/core.py"].replace("    from pkg import orphan\n", "    from pkg import store\n"),
        "pkg/orphan.py": None,
    }
    repo.git("rm", "-q", "pkg/orphan.py")
    repo.git("commit", "-q", "-m", "drop orphan")
    repo.commit({"pkg/core.py": fixed["pkg/core.py"]})
    allowed = DECLARATION + '[[edges]]\nfrom = "core"\nto = "store"\nkinds = ["type-only"]\n'
    repo.commit({".pipelines/components.toml": allowed})
    refresh(repo)
    assert repo.run("test-quality") == 0
    refresh(
        repo,
        receipts=[{"test_id": "tests/test_core.py::test_property", "kind": "property", "outcome": "passed", "seed": 1}],
    )
    assert repo.run("test-quality") == 1
    assert "missing-integration-proof" in capsys.readouterr().out


# spec: PIPE-PAGES-R021.10
def test_a_consumer_without_declarations_is_refused_not_passed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    repo.commit({"pkg/__init__.py": "", "coverage.json": json.dumps({"totals": {"percent_covered": 95}})})
    assert repo.run("test-quality") == 0
    assert repo.run("test-quality", "--require-declared") == 2
    assert "has no component declaration" in capsys.readouterr().err
