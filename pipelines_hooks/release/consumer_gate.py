"""``consumer-gate``: each consumer's tests pass against the release candidate before the producer tags (PIPE-RELEASE-R031).

The consumer manifest is JSON, already in dependency order (the order of the release plan)::

    {"consumers": [{"name": "x", "path": "../x", "install": ["pip", "install", "{candidate}"], "test": ["pytest", "-q"]}]}

Exit 1 names each failing consumer and its first failing test. An empty consumer list for a contract change exits 1.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.release.declared import table

Execute = Callable[[Sequence[str], Path], tuple[int, str]]
_FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.MULTILINE)


def first_failure(output: str) -> str:
    """The first failing test of a pytest-style report, else the last non-empty output line."""
    found = _FAILED.search(output)
    if found:
        return found.group(1)
    lines = [line for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else "no output"


def run(consumers: list[dict], candidate: str, execute: Execute, base: Path, contract_change: bool) -> list[str]:
    """One finding per failing consumer; an empty list for a contract change is itself a finding."""
    if not consumers:
        return ["no consumers are declared for a contract change"] if contract_change else []
    failures = []
    for consumer in consumers:
        where = (base / consumer["path"]).resolve()
        install = [part.replace("{candidate}", candidate) for part in consumer["install"]]
        code, output = execute(install, where)
        if code:
            failures.append(f"{consumer['name']}: the candidate does not install: {first_failure(output)}")
            continue
        code, output = execute(consumer["test"], where)
        if code:
            failures.append(f"{consumer['name']}: {first_failure(output)}")
    return failures


def _execute(argv: Sequence[str], cwd: Path) -> tuple[int, str]:
    done = subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout + done.stderr


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--consumers", type=Path, default=None, help="default: [tool.pipelines.consumer_gate].consumers"
    )
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--contract-change", action="store_true")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    path = args.consumers or root / table(root, "consumer_gate").get("consumers", "consumers.json")
    try:
        consumers = json.loads(Path(path).read_text(encoding="utf-8")).get("consumers", [])
    except (OSError, ValueError) as exc:
        raise CannotRun(f"consumer manifest unreadable: {exc}") from exc
    failures = run(consumers, args.candidate, _execute, Path(path).parent, args.contract_change)
    for failure in failures:
        print(f"CONSUMER_FAILED {failure}", file=sys.stderr)
    return 1 if failures else 0
