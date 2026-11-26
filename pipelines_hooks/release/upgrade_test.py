"""``upgrade-test``: stored data upgrades from the last production release (PIPE-RELEASE-R030).

Installs the last production release into a fresh environment, writes every declared fixture through its public
interface, upgrades the same environment in place to the release candidate and reads every fixture back.

Declared in ``[tool.pipelines.upgrade_test]``::

    package = "dist-name"
    [[tool.pipelines.upgrade_test.fixtures]]
    kind = "records"
    write = ["{python}", "-m", "mypkg.fixture", "write", "{data}"]
    read = ["{python}", "-m", "mypkg.fixture", "read", "{data}"]

Exit 1 names the record kind, the old version and the failed read. A missing last release exits 2.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, repo_root
from pipelines_hooks.release.declared import table

_RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

Install = Callable[[Path, str], None]
Execute = Callable[[Sequence[str]], tuple[int, str]]


def latest_production_tag(root: Path) -> str:
    """The highest ``vX.Y.Z`` tag (a release candidate or pre-release tag never counts)."""
    versions = {}
    for tag in git_text(root, ["tag", "--list", "v*"]).split():
        match = _RELEASE_TAG.match(tag)
        if match:
            versions[tuple(int(n) for n in match.groups())] = tag
    if not versions:
        raise CannotRun("no production release tag exists to upgrade from")
    return versions[max(versions)].removeprefix("v")


def run(declaration: dict, from_version: str, candidate: str, install: Install, execute: Execute) -> list[str]:
    """Failures after an in-place upgrade; empty when every fixture reads back."""
    fixtures = declaration.get("fixtures", [])
    if not fixtures or not declaration.get("package"):
        raise CannotRun("declare a package and at least one fixture under [tool.pipelines.upgrade_test]")
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="upgrade-test-") as tmp:
        venv, data = Path(tmp) / "venv", Path(tmp) / "data"
        data.mkdir()
        install(venv, f"{declaration['package']}=={from_version}")
        python = str(venv / "bin" / "python")

        def argv(template: Sequence[str]) -> list[str]:
            return [part.replace("{python}", python).replace("{data}", str(data)) for part in template]

        for fixture in fixtures:
            code, output = execute(argv(fixture["write"]))
            if code:
                raise CannotRun(f"fixture {fixture['kind']} could not be written by {from_version}: {output.strip()}")
        install(venv, candidate)
        for fixture in fixtures:
            code, output = execute(argv(fixture["read"]))
            if code:
                failures.append(
                    f"{fixture['kind']}: written by {from_version}, read failed after upgrade: {output.strip()}"
                )
    return failures


def _install(venv: Path, spec: str) -> None:
    if not venv.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "install", "--quiet", "--upgrade", spec], check=True)


def _execute(argv: Sequence[str]) -> tuple[int, str]:
    done = subprocess.run(list(argv), capture_output=True, text=True, check=False)
    return done.returncode, done.stdout + done.stderr


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--from-version", default="", help="default: the latest production tag")
    parser.add_argument("--candidate", required=True, help="the release candidate wheel path or requirement")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    try:
        failures = run(
            table(root, "upgrade_test"),
            args.from_version or latest_production_tag(root),
            args.candidate,
            _install,
            _execute,
        )
    except subprocess.CalledProcessError as exc:
        raise CannotRun(f"installation failed: {exc}") from exc
    for failure in failures:
        print(f"UPGRADE_READ_FAILED {failure}", file=sys.stderr)
    return 1 if failures else 0
