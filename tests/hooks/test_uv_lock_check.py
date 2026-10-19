"""uv-lock-check: verify uv.lock against pyproject.toml without mutating it (PRECOMMIT standard)."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from tests.hooks.conftest import Repo

PYPROJECT = '[project]\nname = "fixture"\nversion = "{version}"\nrequires-python = ">=3.10"\ndependencies = []\n'

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")


def test_uv_lock_check_passes_without_a_lockfile(repo: Repo) -> None:
    assert repo.run("uv-lock-check") == 0


def test_uv_lock_check_fails_on_a_stale_lock_and_never_rewrites_it(repo: Repo) -> None:
    repo.write("pyproject.toml", PYPROJECT.format(version="1.0.0"))
    subprocess.run(["uv", "lock", "--offline"], cwd=repo.root, check=True, capture_output=True)
    assert repo.run("uv-lock-check", "--offline") == 0
    lock = (repo.root / "uv.lock").read_text(encoding="utf-8")
    repo.write("pyproject.toml", PYPROJECT.format(version="2.0.0"))
    assert repo.run("uv-lock-check", "--offline") == 1
    assert (repo.root / "uv.lock").read_text(encoding="utf-8") == lock
