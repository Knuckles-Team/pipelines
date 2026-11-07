"""The suite never inherits a git hook's repository selectors."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tests.git_fixture_environment import ROUTING


def test_hook_git_routing_is_cleared_for_every_test(tmp_path: Path) -> None:
    assert not [key for key in ROUTING if key in os.environ]
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=tmp_path, check=True, capture_output=True, text=True
    )
    assert Path(top.stdout.strip()).resolve() == tmp_path.resolve()
