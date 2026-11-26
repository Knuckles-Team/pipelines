"""PIPE-PAGES-R032: lossless workflow export-import with exact version refusal."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.validation.export_version import ExportHeader, Verdict, compare_export_version

CONDITION = "fresh only at the exported version"


def _header(tmp_path: Path, version: str = "3.3.0", condition: str | None = CONDITION) -> Path:
    body: dict[str, str] = {"exported_version": version}
    if condition is not None:
        body["decision_condition"] = condition
    path = tmp_path / "header.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _cli(header: Path, current: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--frozen", "pipelines-hook", "export-version", "--header", str(header), "--current", current],
        capture_output=True,
        text=True,
        check=False,
    )


# spec: PIPE-PAGES-R032.1
def test_export_header_carries_version_and_decision_condition() -> None:
    header = ExportHeader("3.3.0", CONDITION)
    assert (header.exported_version, header.decision_condition) == ("3.3.0", CONDITION)
    assert {verdict.name for verdict in Verdict} == {"SAME", "OLDER", "NEWER"}


# spec: PIPE-PAGES-R032.2
def test_roundtrip_keeps_decision_condition_and_compares_exactly() -> None:
    header = ExportHeader("3.3.0", CONDITION)
    assert compare_export_version(header, "3.3.0") is Verdict.SAME
    assert header.decision_condition == CONDITION
    # No prefix or range match: a patch move is not the same version.
    assert compare_export_version(header, "3.3") is Verdict.NEWER
    assert compare_export_version(header, "3.3.0.1") is Verdict.OLDER
    assert compare_export_version(header, "3.3.1") is Verdict.OLDER
    assert compare_export_version(header, "3.2.9") is Verdict.NEWER


# spec: PIPE-PAGES-R032.3
def test_gate_is_registered_in_the_cli(tmp_path: Path) -> None:
    assert GATES["export-version"] == "pipelines_hooks.validation.export_version"
    assert _cli(_header(tmp_path), "3.3.0").returncode == 0


# spec: PIPE-PAGES-R032.4
def test_version_move_and_lost_condition_refuse_the_import(tmp_path: Path) -> None:
    assert _cli(_header(tmp_path, "3.2.0"), "3.3.0").returncode == 1
    assert _cli(_header(tmp_path, "3.4.0"), "3.3.0").returncode == 1
    lost = _cli(_header(tmp_path, "3.3.0", None), "3.3.0")
    assert lost.returncode == 1 and "lost its decision condition" in lost.stdout
    assert _cli(_header(tmp_path, "3.3.0", "  "), "3.3.0").returncode == 1


# spec: PIPE-PAGES-R032.5
def test_each_roundtrip_prints_its_comparison_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from pipelines_hooks.validation import export_version

    assert export_version.main(["--header", str(_header(tmp_path, "3.2.0")), "--current", "3.3.0"]) == 1
    first = capsys.readouterr().out.splitlines()[0]
    assert json.loads(first) == {"exported_version": "3.2.0", "current": "3.3.0", "verdict": "OLDER"}


# spec: PIPE-PAGES-R032.6
def test_export_import_cli_equal_older_and_newer(tmp_path: Path) -> None:
    same, older, newer = (
        _cli(_header(tmp_path, "3.3.0"), "3.3.0"),
        _cli(_header(tmp_path, "3.2.0"), "3.3.0"),
        _cli(_header(tmp_path, "3.4.0"), "3.3.0"),
    )
    assert (same.returncode, older.returncode, newer.returncode) == (0, 1, 1)
    assert json.loads(newer.stdout.splitlines()[0])["verdict"] == "NEWER"
    assert _cli(tmp_path / "missing.json", "3.3.0").returncode == 2
