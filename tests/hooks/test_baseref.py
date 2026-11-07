"""PIPE-GATES-R096: a branch that merged main is measured from main's fork point."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.core.baseref import upstream_base


def _git(root: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "PATH": "/usr/bin:/bin",
        "HOME": str(root),
    }
    return subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True, text=True).stdout.strip()


def _commit(root: Path, name: str) -> str:
    (root / name).write_text(name + "\n", encoding="utf-8")
    _git(root, "add", "--", name)
    _git(root, "commit", "-q", "-m", name)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def branch_behind_main(tmp_path: Path) -> tuple[Path, str]:
    """A branch pushed at ``pushed``, then main moves and the branch merges it."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _commit(root, "base.txt")
    _git(root, "checkout", "-q", "-b", "topic")
    pushed = _commit(root, "topic.txt")
    _git(root, "checkout", "-q", "main")
    main_tip = _commit(root, "main.txt")
    _git(root, "update-ref", "refs/remotes/origin/main", main_tip)
    _git(root, "checkout", "-q", "topic")
    _git(root, "merge", "-q", "--no-edit", "main")
    return root, pushed


@pytest.mark.spec("PIPE-GATES-R096")
def test_a_push_after_merging_main_is_measured_from_the_main_fork_point(
    branch_behind_main: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, pushed = branch_behind_main
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", pushed)
    assert upstream_base(root, None) == _git(root, "rev-parse", "origin/main")


@pytest.mark.spec("PIPE-GATES-R096")
def test_a_push_without_a_main_merge_keeps_the_pushed_over_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    base = _commit(root, "base.txt")
    _git(root, "update-ref", "refs/remotes/origin/main", base)
    _git(root, "checkout", "-q", "-b", "topic")
    pushed = _commit(root, "one.txt")
    _commit(root, "two.txt")
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", pushed)
    assert upstream_base(root, None) == pushed
