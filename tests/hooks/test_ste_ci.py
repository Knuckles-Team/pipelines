"""Real Git proofs that hosted STE checks committed changes on clean indexes."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from tests.hooks.conftest import Repo

CLEAN = "# Fixture\n\nThe tool runs the hook.\n"
DEBT = "The tool utilizes the wheel.\n"


def _event(repo: Repo, monkeypatch: pytest.MonkeyPatch, *, event: str, base: str) -> None:
    payload = {"pull_request": {"base": {"sha": base}}} if event == "pull_request" else {"before": base}
    path = repo.write("event.json", json.dumps(payload))
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))


@pytest.mark.parametrize("event", ["pull_request", "push"])
@pytest.mark.parametrize("text,expected", [(CLEAN + DEBT, 1), (CLEAN + "The gate checks the file.\n", 0)])
def test_hosted_clean_index_checks_committed_range(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, event: str, text: str, expected: int
) -> None:
    # spec: PIPE-CONNSPEC-R007
    base = repo.commit({"README.md": CLEAN})
    repo.commit({"README.md": text})
    assert not repo.git("diff", "--cached", "--name-only")
    _event(repo, monkeypatch, event=event, base=base)
    assert repo.run("ste-staged") == expected


@pytest.mark.parametrize("extra,expected", [("The gate checks the file.\n", 0), (DEBT, 1)])
def test_ci_range_subtracts_existing_per_message_debt(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], extra: str, expected: int
) -> None:
    base = repo.commit({"README.md": CLEAN + DEBT})
    repo.commit({"README.md": "\n" + CLEAN + DEBT + extra})
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", base)
    assert repo.run("ste-staged") == expected
    assert capsys.readouterr().out.count("utilizes -> use") == expected


def test_local_index_wins_over_ambient_range_and_worktree(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base = repo.commit({"README.md": CLEAN})
    repo.commit({"README.md": CLEAN + DEBT})
    repo.stage({"README.md": CLEAN})
    repo.write("README.md", CLEAN + DEBT + DEBT)
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", base)
    assert repo.run("ste-staged") == 0


def test_local_alternate_index_is_preserved(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    repo.commit({"README.md": CLEAN})
    alternate = repo.root / "alternate.index"
    shutil.copyfile(repo.root / ".git" / "index", alternate)
    repo.write("README.md", CLEAN + DEBT)
    monkeypatch.setenv("GIT_INDEX_FILE", str(alternate))
    subprocess.run(["git", "add", "README.md"], cwd=repo.root, check=True)
    assert repo.run("ste-staged") == 1
    monkeypatch.delenv("GIT_INDEX_FILE")
    assert repo.run("ste-staged") == 0


def test_hosted_range_ignores_staged_and_worktree_edits(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base = repo.commit({"README.md": CLEAN})
    repo.commit({"README.md": CLEAN + DEBT})
    repo.stage({"README.md": CLEAN})
    _event(repo, monkeypatch, event="pull_request", base=base)
    assert repo.run("ste-staged") == 1


@pytest.mark.parametrize("source", ["argument", "pre-commit", "event"])
def test_missing_requested_base_fails_closed(repo: Repo, monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    repo.commit({"README.md": CLEAN})
    args = ["--base-ref", "missing-base"] if source == "argument" else []
    if source == "pre-commit":
        monkeypatch.setenv("PRE_COMMIT_FROM_REF", "missing-base")
    if source == "event":
        _event(repo, monkeypatch, event="pull_request", base="f" * 40)
    assert repo.run("ste-staged", *args) == 2


@pytest.mark.parametrize("payload", ["{}", "[]", "not JSON", '{"before": 123}', '{"before": ""}', '{"before": "HEAD"}'])
def test_bad_ci_event_fails_closed(repo: Repo, monkeypatch: pytest.MonkeyPatch, payload: str) -> None:
    path = repo.write("event.json", payload)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
    assert repo.run("ste-staged") == 2


def test_ci_needs_readable_event_unless_explicit_base(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base = repo.commit({"README.md": CLEAN})
    repo.commit({"README.md": CLEAN + DEBT})
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    assert repo.run("ste-staged") == 2
    assert repo.run("ste-staged", "--base-ref", base) == 1


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
@pytest.mark.parametrize("initial", [True, False])
def test_new_ref_and_manual_runs_check_last_commit(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, event: str, initial: bool
) -> None:
    if initial:
        repo.git("checkout", "--orphan", "first")
        repo.git("rm", "-rf", ".")
    else:
        repo.commit({"README.md": CLEAN})
    head = repo.commit({"README.md": CLEAN + DEBT})
    _event(repo, monkeypatch, event=event, base="0" * 40)
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", head)
    assert repo.run("ste-staged") == 1


def test_pr_event_cannot_be_narrowed_by_ambient_ref(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base = repo.commit({"README.md": CLEAN})
    head = repo.commit({"README.md": CLEAN + DEBT})
    _event(repo, monkeypatch, event="pull_request", base=base)
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", head)
    assert repo.run("ste-staged") == 1


def test_new_ref_shallow_history_fails_closed(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    head = repo.commit({"README.md": CLEAN + DEBT})
    repo.write(".git/shallow", head + "\n")
    _event(repo, monkeypatch, event="push", base="0" * 40)
    assert repo.run("ste-staged") == 2
