"""Invoke the strict repository-manager release checker without installing it."""

from __future__ import annotations

import argparse
import subprocess
import sys

from pipelines_hooks.core.errors import CannotRun


def main(argv: list[str]) -> int:
    """Delegate to an already prepared RM interpreter; any failure blocks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable,
                        help="prepared repository-manager interpreter (no downloads)")
    args = parser.parse_args(argv)
    try:
        result = subprocess.run(
            [args.python, "-I", "-m", "repository_manager.release_readiness_hook", "."],
            check=False,
        )
    except OSError as exc:
        raise CannotRun(f"repository-manager interpreter unavailable: {exc}") from exc
    if result.returncode:
        raise CannotRun("authoritative release checker failed or is unavailable; "
                        "prepare repository-manager in the selected interpreter")
    return 0
