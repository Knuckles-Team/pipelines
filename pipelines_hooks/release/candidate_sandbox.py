"""``candidate-sandbox``: smoke the candidate once, then publish exactly those artifacts (PIPE-RELEASE-R032).

Subcommands: ``build`` records the sha256 of every candidate artifact; ``smoke`` starts the candidate in a disposable
environment and runs the smoke steps; ``verify`` compares the artifacts about to publish with the recorded digests.

Declared in ``[tool.pipelines.candidate_sandbox]``: ``build`` (argv), ``artifacts`` (glob list), ``start`` (argv, run in
the background and stopped after the pass) and ``steps`` (a table of step name to argv). A failed step exits 1 and names
the step; a digest that differs from the recorded digest exits 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.release.declared import table

DEFAULT_STEPS = ("health", "sign-in", "write", "read", "tool-call")
Execute = Callable[[Sequence[str]], int]


def digests(root: Path, patterns: Sequence[str]) -> dict[str, str]:
    """Artifact name -> sha256 for every file matching the globs."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for pat in patterns for p in sorted(root.glob(pat))}


def build(root: Path, declaration: dict, record: Path, execute: Execute) -> int:
    """Build the candidate artifacts once and record their digests."""
    if execute(declaration["build"]):
        raise CannotRun("the candidate build failed")
    found = digests(root, declaration["artifacts"])
    if not found:
        raise CannotRun("the candidate build produced no artifact")
    record.write_text(json.dumps(found, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def smoke(steps: dict[str, list[str]], names: Sequence[str], execute: Execute) -> list[str]:
    """The first failed smoke step, as a one-item list; empty when every step passes."""
    for name in names:
        if name not in steps:
            return [f"{name}: the step is not declared"]
        if execute(steps[name]):
            return [f"{name}: the smoke step failed"]
    return []


def verify(recorded: dict[str, str], actual: dict[str, str]) -> list[str]:
    """Publish digests that differ from, or are absent in, the recorded digests."""
    problems = [
        f"{n}: publish digest differs from the built digest" for n, d in sorted(actual.items()) if recorded.get(n) != d
    ]
    problems += [f"{n}: recorded artifact is not published" for n in sorted(set(recorded) - set(actual))]
    return problems


def _executor(root: Path) -> Execute:
    return lambda argv: subprocess.run(list(argv), cwd=root, check=False).returncode


def _smoke_run(root: Path, declaration: dict, names: Sequence[str]) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="candidate-sandbox-"):
        server = subprocess.Popen(declaration["start"], cwd=root)  # noqa: S603 - the declared start command
        try:
            return smoke(declaration["steps"], names, _executor(root))
        finally:
            server.terminate()
            server.wait(timeout=30)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "smoke", "verify"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--digests", type=Path, default=Path("candidate-digests.json"))
    parser.add_argument("--smoke-steps", default=",".join(DEFAULT_STEPS))
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    declaration = table(root, "candidate_sandbox")
    if not declaration:
        raise CannotRun("declare [tool.pipelines.candidate_sandbox] to run the candidate sandbox")
    record = root / args.digests
    if args.command == "build":
        return build(root, declaration, record, _executor(root))
    problems = (
        _smoke_run(root, declaration, [s for s in args.smoke_steps.split(",") if s])
        if args.command == "smoke"
        else verify(json.loads(record.read_text(encoding="utf-8")), digests(root, declaration["artifacts"]))
    )
    for problem in problems:
        print(f"CANDIDATE_REFUSED {problem}", file=sys.stderr)
    return 1 if problems else 0
