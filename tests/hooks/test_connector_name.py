"""PIPE-GATES-R010: connector name literals agree with the declared fleet name."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.hygiene import connector_name

pytestmark = pytest.mark.spec("PIPE-GATES-R010")

_DECLARED = (
    '[project]\nname = "demo-api"\n[project.entry-points."agent_connector_sdk.connector"]\ndemo-mcp = "demo_api"\n'
)


def _connector(root: Path, *, pyproject: str, name: str) -> Path:
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    package = root / "demo_api"
    (package / "connectors").mkdir(parents=True)
    (package / "connector_manifest.yml").write_text(f"connector: {name}\n", encoding="utf-8")
    (package / "connectors" / "tool_schema_fingerprints.json").write_text(
        f'{{"connector": "{name}", "tools": {{}}}}', encoding="utf-8"
    )
    (package / "kg_ingest.py").write_text(
        f'_BINDING = IngestBinding(\n    connector="{name}", stream="demo"\n)\n', encoding="utf-8"
    )
    return root


def test_agreeing_literals_pass(tmp_path: Path) -> None:
    root = _connector(tmp_path, pyproject=_DECLARED, name="demo-mcp")
    assert connector_name.main(["--root", str(root)]) == 0


def test_a_disagreeing_literal_fails_and_names_the_file(tmp_path: Path, capsys) -> None:
    root = _connector(tmp_path, pyproject=_DECLARED, name="demo-api")
    assert connector_name.main(["--root", str(root)]) == 1
    output = capsys.readouterr().out
    for path in ("connector_manifest.yml", "tool_schema_fingerprints.json", "kg_ingest.py"):
        assert path in output


def test_undeclared_connector_warns_unless_strict(tmp_path: Path, capsys) -> None:
    root = _connector(tmp_path, pyproject='[project]\nname = "demo-api"\n', name="demo-api")
    assert connector_name.main(["--root", str(root)]) == 0
    assert "WARN" in capsys.readouterr().out
    assert connector_name.main(["--root", str(root), "--strict"]) == 1


def test_non_connector_repository_passes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert connector_name.main(["--root", str(tmp_path), "--strict"]) == 0
