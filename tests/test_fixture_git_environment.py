"""Disposable fixture Git commands must not inherit a hook's parent repository."""

from pathlib import Path

import pytest

from pipelines_hooks.core.gitenv import git_text
from tests.pages_fleet_fixtures import git as fleet_git
from tests.test_maturin_pipeline_contract import _git as maturin_git
from tests.workflow_fixtures import runtime_checkout


@pytest.mark.parametrize("fixture_git", [fleet_git, maturin_git], ids=["pages", "maturin"])
def test_fixture_git_preserves_parent_under_inherited_selectors(tmp_path: Path, monkeypatch, fixture_git) -> None:
    outer = tmp_path / "outer"
    inner = tmp_path / "inner"
    outer.mkdir()
    inner.mkdir()
    original_head = runtime_checkout(outer)
    sentinel = outer / "parent.txt"
    sentinel.write_text("Keep the parent's staged source and metadata.\n")
    git_text(outer, ("add", "--", "parent.txt"))
    protected = {path: path.read_bytes() for path in (sentinel, outer / ".git/index", outer / ".git/config")}
    contamination = {
        "GIT_DIR": str(outer / ".git"), "GIT_COMMON_DIR": str(outer / ".git"),
        "GIT_WORK_TREE": str(outer), "GIT_INDEX_FILE": str(outer / ".git/index"),
        "GIT_OBJECT_DIRECTORY": str(outer / ".git/objects"),
        "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "inherited-name",
    }
    for key, value in contamination.items():
        monkeypatch.setenv(key, value)
    fixture_git(inner, "init", "-q")
    fixture_git(inner, "config", "user.name", "inner-fixture")
    (inner / "inner.txt").write_text("This file belongs only to the disposable inner repository.\n")
    fixture_git(inner, "add", "--", "inner.txt")
    assert fixture_git(inner, "rev-parse", "--show-toplevel") == str(inner)
    assert fixture_git(inner, "config", "--get", "user.name") == "inner-fixture"
    assert fixture_git(inner, "ls-files") == "inner.txt"
    assert git_text(outer, ("rev-parse", "HEAD")).strip() == original_head
    assert {path: path.read_bytes() for path in protected} == protected
