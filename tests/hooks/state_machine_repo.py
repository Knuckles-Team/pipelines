"""A throwaway git repository built from one state-machine fixture directory."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "state_machine"
POLICY = '[tool.pipelines_hooks.state_machine]\npaths = ["pkg", "src"]\nmode = "{mode}"\n{extra}'


def git(root: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "PATH": "/usr/bin:/bin",
        "HOME": str(root),
    }
    done = subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True, text=True)
    return done.stdout


def fixture_repo(tmp: Path, *cases: str, mode: str = "blocking", extra: str = "", policy: bool = True) -> Path:
    """Copy ``<lang>/<case>`` fixtures into one repository and commit them."""
    root = tmp / "repo"
    root.mkdir(parents=True)
    for case in cases:
        shutil.copytree(FIXTURES / case, root, dirs_exist_ok=True)
    if policy:
        (root / "pyproject.toml").write_text(POLICY.format(mode=mode, extra=extra), encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    return root
