"""uv-lock-check: ``uv.lock`` agrees with ``pyproject.toml`` (pre-push; verify, never mutate).

Runs ``uv lock --check``, which resolves without writing and exits non-zero
when the lockfile would change. A repository without ``uv.lock`` passes.
``--root`` selects the repository (default: the working directory); every
other argument (for example ``--offline``) passes through to uv.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from pipelines_hooks.core.errors import Unavailable


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="uv-lock-check", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments, passthrough = parser.parse_known_args(argv)
    root: Path = arguments.root
    if not (root / "uv.lock").is_file():
        print("uv-lock-check: no uv.lock; nothing to verify")
        return 0
    uv = shutil.which("uv")
    if uv is None:
        raise Unavailable("uv is not on PATH", remedy="https://docs.astral.sh/uv/ (install uv)")
    completed = subprocess.run([uv, "lock", "--check", *passthrough], cwd=root, check=False)
    if completed.returncode != 0:
        print("uv-lock-check: uv.lock is stale; run `uv lock` and commit the result")
        return 1
    return 0
