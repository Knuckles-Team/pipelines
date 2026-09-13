"""Verify the checked-out commit before and after a package build."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--verify", "HEAD"],
        text=True,
    ).strip()


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _before(expected: str) -> int:
    source = _head()
    if not expected or source != expected:
        return _fail(
            f"checked-out commit {source} does not match github.sha {expected}"
        )
    environment_file = os.environ.get("GITHUB_ENV")
    if not environment_file:
        return _fail("GITHUB_ENV is required to bind SOURCE_COMMIT")
    with Path(environment_file).open("a", encoding="utf-8", newline="") as stream:
        stream.write(f"SOURCE_COMMIT={source}\n")
    print(f"Building from commit: {source}")
    return 0


def _after() -> int:
    source = os.environ.get("SOURCE_COMMIT")
    current = _head()
    if not source or current != source:
        return _fail("HEAD changed while building the package")
    print(f"HEAD unchanged after build: {current}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return _fail("usage: verify_source_commit.py before|after")
    if argv[1] == "before":
        return _before(os.environ.get("EXPECTED_COMMIT", ""))
    if argv[1] == "after":
        return _after()
    return _fail(f"unknown phase: {argv[1]}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
