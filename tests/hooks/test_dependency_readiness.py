"""The shared RELEASE hook delegates and fails closed even outside CI."""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from pipelines_hooks.cli import run_gate
from pipelines_hooks.release import dependency_readiness as gate
from tests.hooks.test_catalogue import _catalogue


def test_release_stage_owned_by_catalogue():
    assert _catalogue()["dependency-readiness"]["stages"] == ["manual"]


def test_authoritative_checker_invocation(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(gate.subprocess, "run", run)
    assert run_gate("dependency-readiness", ["--python", "/prepared/python"]) == 0
    assert calls == [(["/prepared/python", "-I", "-m",
                      "repository_manager.release_readiness_hook", "."], {"check": False})]


@pytest.mark.parametrize("code", [1, 2, -9])
def test_checker_failure_never_skipped(monkeypatch, code):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=code))
    assert run_gate("dependency-readiness", []) == 2


def test_missing_interpreter_never_skipped(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    assert run_gate("dependency-readiness", ["--python", str(tmp_path / "missing")]) == 2


def test_missing_checker_in_real_isolated_environment(tmp_path):
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(tmp_path / "venv")], check=True)
    python = tmp_path / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    assert run_gate("dependency-readiness", ["--python", str(python)]) == 2
