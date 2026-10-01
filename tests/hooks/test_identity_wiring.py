"""commit-identity fail-closed diagnostics (FR-5, N-5) and CLI registration.

Every identity here is an obviously synthetic ``*.invalid`` fixture, never a
real contributor.
"""

from __future__ import annotations

import pytest

from pipelines_hooks.cli import GATES, main as cli_main
from tests.hooks.conftest import Repo, write_identity_allowlist

ALLOWED = {"name": "Example Author", "email": "author@example.invalid"}


def test_n5_a_missing_allowlist_fails_closed_in_ci(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    assert repo.run("commit-identity-range") == 2


def test_n5_a_missing_allowlist_is_a_visible_local_skip_naming_the_remedy(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CI", "false")
    assert repo.run("commit-identity-range") == 0
    err = capsys.readouterr().err
    assert "SKIPPED (commit-identity-range)" in err
    assert "COMMIT_IDENTITY_ALLOWLIST" in err or "commit-identity-allowlist.json" in err


def test_n5_a_malformed_allowlist_always_fails_regardless_of_ci(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    write_identity_allowlist(repo.root, [])
    monkeypatch.setenv("CI", "false")
    assert repo.run("commit-identity-range") == 2
    monkeypatch.setenv("CI", "true")
    assert repo.run("commit-identity-range") == 2


def test_both_gates_are_registered_in_the_cli() -> None:
    assert GATES["commit-identity"] == "pipelines_hooks.identity.commit_gate"
    assert GATES["commit-identity-range"] == "pipelines_hooks.identity.range_gate"


def test_commit_identity_is_invocable_through_the_cli_entrypoint(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "false")
    monkeypatch.chdir(repo.root)
    assert cli_main(["commit-identity"]) == 0  # nothing staged: proves the id resolves and runs


def test_commit_identity_range_is_invocable_through_the_cli_entrypoint(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_identity_allowlist(repo.root, [ALLOWED])
    monkeypatch.setenv("CI", "false")
    monkeypatch.chdir(repo.root)
    assert cli_main(["commit-identity-range", "--base", "HEAD"]) == 0
