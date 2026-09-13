"""Verify the checked-out commit before and after a package build."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _head(repository: Path | None = None) -> str:
    command = ["git"]
    if repository is not None:
        command.extend(["-C", str(repository)])
    command.extend(["rev-parse", "--verify", "HEAD"])
    return subprocess.check_output(
        command,
        text=True,
    ).strip()


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _contract_commit(expected: str) -> str | None:
    contract_path = Path(os.environ.get("PIPELINES_CONTRACT_PATH", ".pipeline-contract"))
    if not contract_path.is_dir():
        _fail(f"pipeline contract checkout is missing: {contract_path}")
        return None
    contract = _head(contract_path)
    if not expected or contract != expected:
        _fail(
            "pipeline contract commit "
            f"{contract} does not match the reusable workflow commit {expected}"
        )
        return None
    return contract


def _before(expected: str) -> int:
    source = _head()
    if not expected or source != expected:
        return _fail(
            f"checked-out commit {source} does not match github.sha {expected}"
        )
    contract = _contract_commit(os.environ.get("EXPECTED_WORKFLOW_COMMIT", ""))
    if contract is None:
        return 1
    environment_file = os.environ.get("GITHUB_ENV")
    if not environment_file:
        return _fail("GITHUB_ENV is required to bind release provenance")
    with Path(environment_file).open("a", encoding="utf-8", newline="") as stream:
        stream.write(f"SOURCE_COMMIT={source}\n")
        stream.write(f"PIPELINES_CONTRACT_COMMIT={contract}\n")
    print(f"Building from commit: {source}")
    print(f"Using pipeline contract commit: {contract}")
    return 0


def _after() -> int:
    source = os.environ.get("SOURCE_COMMIT")
    current = _head()
    if not source or current != source:
        return _fail("HEAD changed while building the package")
    contract = os.environ.get("PIPELINES_CONTRACT_COMMIT")
    current_contract = _contract_commit(os.environ.get("EXPECTED_WORKFLOW_COMMIT", ""))
    if current_contract is None or not contract or current_contract != contract:
        return _fail("pipeline contract changed while building the package")
    print(f"HEAD unchanged after build: {current}")
    print(f"Pipeline contract unchanged after build: {current_contract}")
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
