"""fast-tests: the affected tests only, under a hard wall-clock cap (pre-push).

Wraps ``pr-test-scope`` (CI-STANDARD pre-push): the base is the hook's
``PRE_COMMIT_FROM_REF`` (set by ``pre-commit --from-ref``) unless ``--base-ref``
is given. ``NONE`` and ``FULL`` run nothing locally -- the full suite belongs to
main CI -- and say so. A selected subset, minus tests marked ``browser``, runs under ``--timeout`` seconds
(default 120); exceeding it fails the hook (exit 1) rather than hanging a push.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET  # noqa: S405 - the file is written by our own pytest run
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
    parser.add_argument("--src-root", default="arbora")
    parser.add_argument("--tests-root", default="tests")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


#: Browser tests drive a real headless browser and are slow by nature: a repository's own browser workflow proves them.
DESELECT_MARKER = "not browser"


def _pytest_command(root: Path, tests: list[str]) -> list[str]:
    selection = ["-q", "-x", "-m", DESELECT_MARKER, *tests]
    if (root / "uv.lock").is_file() and shutil.which("uv"):
        return ["uv", "run", "--frozen", "pytest", *selection]
    return [sys.executable, "-m", "pytest", *selection]


def _suites_run(report: Path) -> int | None:
    """Tests recorded in a junit report, or None when pytest wrote no readable report."""
    try:
        root = ET.parse(report).getroot()  # noqa: S314 - written by the pytest run above
    except (OSError, ET.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return sum(int(suite.get("tests", "0")) for suite in suites)


def _only_browser_tests(command: list[str], root: Path) -> bool:
    """True when the selection holds browser tests and nothing else (the ``-m`` deselection emptied it)."""
    at = command.index(DESELECT_MARKER)  # the value of the ``-m`` option; the ``-m`` before it is the selector
    probe = [*command[: at - 1], "--collect-only", "-q", "-m", "browser", *command[at + 1 :]]
    return subprocess.run(probe, cwd=root, capture_output=True, check=False).returncode == 0


def require_suites(command: list[str], returncode: int, suites: int | None) -> int:
    """Fail a run that executed zero test suites, whatever the tool's own exit status."""
    if suites == 0 or returncode == 5:  # 5: pytest collected nothing
        print(f"fast-tests: no test suites ran: {' '.join(command)}", file=sys.stderr)
        return 1
    return returncode


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
    command = _pytest_command(root, scope)
    try:
        with tempfile.TemporaryDirectory(prefix="fast-tests-") as tmp:
            report = Path(tmp) / "junit.xml"
            code = subprocess.run(
                [*command, f"--junitxml={report}"], cwd=root, timeout=args.timeout, check=False
            ).returncode
            if code == 5 and _only_browser_tests(command, root):
                print("fast-tests: only browser tests are affected; the repository's browser workflow proves them")
                return 0
            return require_suites(command, code, _suites_run(report))
    except subprocess.TimeoutExpired:
        print(f"fast-tests: exceeded {args.timeout}s; narrow the change or run the suite in CI", file=sys.stderr)
        return 1
