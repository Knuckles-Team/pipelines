"""A missing prerequisite fails closed in CI and is a visible skip locally."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.cli import in_ci, run_gate
from pipelines_hooks.core import tools
from tests.hooks.conftest import Repo


@pytest.fixture
def no_scanners(monkeypatch: pytest.MonkeyPatch) -> None:
    """No pinned scanner resolves anywhere, whatever this host has installed."""
    monkeypatch.setattr(tools, "_executable", lambda candidate: False)
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)


@pytest.mark.parametrize("value", ["true", "1", "yes", "True"])
def test_ci_is_detected_from_any_truthy_value(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CI", value)
    assert in_ci()


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_ci_is_off_for_empty_or_falsy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CI", value)
    assert not in_ci()


def test_missing_scanner_fails_closed_in_ci(no_scanners: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_gate("scanner-versions", ["cccc"]) == 2
    assert "scanner-versions: CANNOT RUN: cccc is not installed" in capsys.readouterr().err


def test_missing_scanner_is_skipped_locally_with_the_remedy(
    no_scanners: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CI")
    assert run_gate("scanner-versions", ["cccc"]) == 0
    err = capsys.readouterr().err
    assert err.startswith("SKIPPED (scanner-versions): cccc is not installed")
    assert err.rstrip().endswith("run scripts/bootstrap.sh --scanners")


def test_a_misconfigured_scanner_path_is_not_downgraded_locally(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit ``$CCCC_BIN`` that is not executable is a defect, not a missing tool."""
    monkeypatch.delenv("CI")
    monkeypatch.setenv("CCCC_BIN", str(tmp_path / "absent-cccc"))
    assert run_gate("scanner-versions", ["cccc"]) == 2


def test_missing_fleet_root_fails_closed_in_ci(repo: Repo, tmp_path: Path) -> None:
    assert run_gate("supply-chain", ["--fleet-root", str(tmp_path / "no-fleet")]) == 2


def test_missing_fleet_root_is_skipped_locally(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CI")
    assert run_gate("supply-chain", ["--fleet-root", str(tmp_path / "no-fleet")]) == 0
    assert "SKIPPED (supply-chain): fleet root" in capsys.readouterr().err


def test_empty_fleet_root_is_skipped_locally(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI")
    (tmp_path / "fleet").mkdir()
    assert run_gate("supply-chain", ["--fleet-root", str(tmp_path / "fleet")]) == 0


def test_missing_snapshot_workspace_is_skipped_locally_and_fails_in_ci(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = ["--source-snapshot-root", str(tmp_path), "--snapshot-workspace", str(tmp_path / "workspace.yml")]
    assert run_gate("supply-chain", arguments) == 2
    monkeypatch.delenv("CI")
    assert run_gate("supply-chain", arguments) == 0


def test_a_present_but_non_authoritative_snapshot_still_fails_locally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only absence is downgraded; a wrong workspace is still exit 2."""
    monkeypatch.delenv("CI")
    workspace = tmp_path / "workspace.yml"
    workspace.write_text("repositories: []\n", encoding="utf-8")
    assert run_gate("supply-chain", ["--source-snapshot-root", str(tmp_path), "--snapshot-workspace", str(workspace)]) == 2
