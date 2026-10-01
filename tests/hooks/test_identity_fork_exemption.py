"""commit-identity-range fork exemption: external pull requests are not checked.

Every identity here is an obviously synthetic ``*.invalid`` fixture, never a
real contributor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.identity.fork_exemption import is_fork_pull_request
from tests.hooks.conftest import Repo, commit_as, write_identity_allowlist

OUTSIDE_NAME = "Outside Contributor"
OUTSIDE_EMAIL = "outside@example.invalid"


def _event_path(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "event.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _pull_request_payload(*, head_repo: str, base_repo: str) -> dict:
    return {
        "pull_request": {
            "head": {"repo": {"full_name": head_repo}},
            "base": {"repo": {"full_name": base_repo}},
        }
    }


def test_same_repository_pull_request_is_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event_path(tmp_path, _pull_request_payload(head_repo="Knuckles-Team/pipelines", base_repo="Knuckles-Team/pipelines"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert is_fork_pull_request() is False


def test_fork_pull_request_is_exempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event_path(tmp_path, _pull_request_payload(head_repo="someone-else/pipelines", base_repo="Knuckles-Team/pipelines"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert is_fork_pull_request() is True


def test_a_push_is_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event_path(tmp_path, _pull_request_payload(head_repo="someone-else/pipelines", base_repo="Knuckles-Team/pipelines"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert is_fork_pull_request() is False


def test_a_local_run_with_no_event_name_is_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert is_fork_pull_request() is False


def test_a_missing_event_payload_is_treated_as_not_exempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "does-not-exist.json"))
    assert is_fork_pull_request() is False


def test_an_unreadable_event_payload_is_treated_as_not_exempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = tmp_path / "broken.json"
    event.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert is_fork_pull_request() is False


def test_a_pull_request_event_with_no_path_set_is_treated_as_not_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert is_fork_pull_request() is False


def test_range_gate_passes_an_exempt_fork_pull_request_with_no_allowlist_configured(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The range gate never even needs the allowlist for an exempt fork PR."""
    base = repo.git("rev-parse", "HEAD").strip()
    commit_as(repo.root, name=OUTSIDE_NAME, email=OUTSIDE_EMAIL, message="fork-contribution")
    event = _event_path(repo.root, _pull_request_payload(head_repo="someone-else/pipelines", base_repo="Knuckles-Team/pipelines"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("CI", "true")
    assert repo.run("commit-identity-range", "--base", base) == 0


def test_range_gate_still_checks_a_same_repository_pull_request(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    write_identity_allowlist(repo.root, [{"name": "Example Author", "email": "author@example.invalid"}])
    commit_as(repo.root, name=OUTSIDE_NAME, email=OUTSIDE_EMAIL, message="same-repo-bad")
    event = _event_path(repo.root, _pull_request_payload(head_repo="Knuckles-Team/pipelines", base_repo="Knuckles-Team/pipelines"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("CI", "true")
    assert repo.run("commit-identity-range", "--base", base) == 1
