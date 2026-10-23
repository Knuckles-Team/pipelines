"""PIPE-GATES-R012: a connector that imports GraphQL declares it via the SDK extra."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.hygiene import connector_graphql

pytestmark = pytest.mark.spec("PIPE-GATES-R012")


def _repo(root: Path, *, dependencies: str, extras: str = "", source: str = "from gql import gql\n") -> Path:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "demo-api"\ndependencies = [{dependencies}]\n[project.optional-dependencies]\n{extras}\n',
        encoding="utf-8",
    )
    package = root / "demo_api"
    package.mkdir()
    (package / "demo_gql.py").write_text(source, encoding="utf-8")
    return root


def test_sdk_graphql_extra_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path, dependencies='"agent-connector-sdk[mcp,graphql]>=0.3.12,<1"')
    assert connector_graphql.findings(root) == []
    assert connector_graphql.main(["--root", str(root), "--strict"]) == 0


def test_missing_extra_warns_by_default_and_fails_strict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, dependencies='"agent-connector-sdk[mcp]>=0.3.8"', source="from graphql import parse\n")
    assert connector_graphql.main(["--root", str(root)]) == 0
    assert "WARN" in capsys.readouterr().out
    assert connector_graphql.main(["--root", str(root), "--strict"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_direct_gql_declarations_are_reported(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        dependencies='"agent-connector-sdk[mcp,graphql]>=0.3.12", "gql[requests]>=4.4.0"',
        extras='gql = ["gql>=4.4.0"]\nall = ["graphql-core>=3.2"]',
    )
    problems = connector_graphql.findings(root)
    assert len(problems) == 3
    assert any("optional-dependencies.gql" in problem for problem in problems)


def test_function_level_import_counts_and_tests_are_skipped(tmp_path: Path) -> None:
    root = _repo(tmp_path, dependencies='"requests"', source="def f():\n    import graphql\n")
    assert connector_graphql.importers(root) == ["demo_api/demo_gql.py"]
    (root / "demo_api" / "demo_gql.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text("import gql\n", encoding="utf-8")
    assert connector_graphql.findings(root) == []


def test_sdk_and_non_python_repositories_pass(tmp_path: Path) -> None:
    assert connector_graphql.findings(tmp_path) == []
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    (sdk / "pyproject.toml").write_text('[project]\nname = "agent-connector-sdk"\n', encoding="utf-8")
    (sdk / "client.py").write_text("import gql\n", encoding="utf-8")
    assert connector_graphql.findings(sdk) == []
