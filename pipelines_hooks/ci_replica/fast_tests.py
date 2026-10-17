"""fast-tests: the affected tests only, under a hard wall-clock cap (pre-push).

Wraps ``pr-test-scope`` (CI-STANDARD pre-push): the base is the hook's
``PRE_COMMIT_FROM_REF`` (set by ``pre-commit --from-ref``) unless ``--base-ref``
is given. ``NONE`` and ``FULL`` run nothing locally -- the full suite belongs to
main CI -- and say so. A selected subset runs under ``--timeout`` seconds
(default 120); exceeding it fails the hook (exit 1) rather than hanging a push.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from pipelines_hooks.ci_replica.test_scope import FULL, NONE, _python_scope
from pipelines_hooks.clones.dupehound import changed_paths
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.settings import setting

DEFAULT_TIMEOUT_SECONDS = 120


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fast-tests", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", default=setting("PRE_COMMIT_FROM_REF"))
    parser.add_argument("--src-root", default="graph_os")
    parser.add_argument("--tests-root", default="tests")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def _pytest_command(root: Path, tests: list[str]) -> list[str]:
    if (root / "uv.lock").is_file() and shutil.which("uv"):
        return ["uv", "run", "--frozen", "pytest", "-q", "-x", *tests]
    return [sys.executable, "-m", "pytest", "-q", "-x", *tests]


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    if args.timeout < 1:
        raise CannotRun("--timeout must be a positive number of seconds")
    root = repo_root(args.root)
    scope = _python_scope(
        root, changed_paths(root, args.base_ref or None), args.src_root.rstrip("/"), args.tests_root.rstrip("/")
    )
    if scope == [NONE]:
        print("fast-tests: no affected tests")
        return 0
    if scope == [FULL]:
        print("fast-tests: shared test infrastructure changed; the full suite runs in main CI")
        return 0
    try:
        return subprocess.run(_pytest_command(root, scope), cwd=root, timeout=args.timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        print(f"fast-tests: exceeded {args.timeout}s; narrow the change or run the suite in CI", file=sys.stderr)
        return 1
