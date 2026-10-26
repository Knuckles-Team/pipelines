"""PIPE-GATES-R011: clone snapshots skip tracked symlinks instead of refusing the tree."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.clones.jscpd_snapshot import materialize

pytestmark = pytest.mark.spec("PIPE-GATES-R011")  # binds cache freshness and symlink snapshot behavior


def _git(root: Path, *args: str) -> str:
    # Drop ambient GIT_* (a pre-push hook exports GIT_DIR for the outer repository).
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env |= {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True, text=True).stdout


def test_a_tracked_symlink_is_skipped_and_its_target_kept(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "pkg" / "connector_manifest.yml").write_text("connector: demo-mcp\n", encoding="utf-8")
    (repo / "connector_manifest.yml").symlink_to("pkg/connector_manifest.yml")
    _git(repo, "add", "pkg/connector_manifest.yml", "connector_manifest.yml")
    _git(repo, "commit", "-q", "-m", "init")
    out = materialize(repo, "HEAD", tmp_path / "snapshot")
    assert (out / "pkg" / "connector_manifest.yml").is_file()
    assert not (out / "connector_manifest.yml").exists()
