"""Throwaway git repositories and in-process gate runs for the shared-hook tests.

Every gate test plants a violation and proves the gate fires (exit 1), then
proves it passes on a clean fixture (exit 0). Gates run the real pinned
scanners; nothing is mocked.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.cli import run_gate
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.core.tools import resolve

#: The runner's own ``CI`` value, captured before the autouse fixture below
#: pins it for gate runs.
RUNNER_IN_CI = (os.environ.get("CI") or "").strip().casefold() not in {"", "0", "false", "no"}

HOOK_REPOSITORY = Path(__file__).resolve().parents[2]
PYPROJECT = '[project]\nname = "fixture"\nversion = "0"\n\n[tool.pipelines_hooks]\npackages = ["pkg"]\n'


class Repo:
    """A git repository under a pytest temporary directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def git(self, *args: str) -> str:
        identity = ["-c", "user.name=hook-test", "-c", "user.email=hooks@example.invalid", "-c", "commit.gpgsign=false"]
        result = subprocess.run(["git", *identity, *args], cwd=self.root, env=sanitized_env(), check=True, capture_output=True, text=True)
        return result.stdout

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self, files: dict[str, str], message: str = "change") -> str:
        for rel, text in files.items():
            self.write(rel, text)
        self.git("add", "--", *files)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def stage(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            self.write(rel, text)
        self.git("add", "--", *files)

    def run(self, gate: str, *args: str) -> int:
        return run_gate(gate, ["--root", str(self.root), *args])


def write_identity_allowlist(root: Path, identities: list[dict[str, str]], version: str = "1") -> Path:
    """A ``.config/commit-identity-allowlist.json`` naming the given synthetic identities."""
    path = root / ".config" / "commit-identity-allowlist.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": version, "identities": identities}), encoding="utf-8")
    return path


def set_local_identity(root: Path, *, name: str, email: str) -> None:
    """Persist ``user.name``/``user.email`` in the repository's own config (not ``-c``).

    Unlike :meth:`Repo.git`'s per-invocation ``-c`` override, this is what a
    fresh ``git var GIT_AUTHOR_IDENT`` call -- run by the commit-time gate as
    its own subprocess -- will actually resolve.
    """
    env = sanitized_env()
    subprocess.run(["git", "config", "user.name", name], cwd=root, env=env, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", email], cwd=root, env=env, check=True, capture_output=True)


def stage_file(root: Path, rel: str = "pending.txt", text: str = "pending\n") -> None:
    """Stage one file without committing it, for a commit-time (pending) check."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", "--", rel], cwd=root, env=sanitized_env(), check=True, capture_output=True)


def commit_as(root: Path, *, name: str, email: str, message: str = "change", author: str | None = None) -> str:
    """A commit made under an explicit, possibly-synthetic identity.

    ``-c user.name=``/``-c user.email=`` sets the committer for this one
    invocation only (matching :mod:`pipelines_hooks.core.gitenv`'s sanitized,
    non-ambient style); ``--author`` records a different author when given.
    """
    stage_file(root, f"identity-{abs(hash(message))}.txt", message)
    env = sanitized_env()
    args = ["git", "-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "commit.gpgsign=false", "commit", "-q", "-m", message]
    if author is not None:
        args.append(f"--author={author}")
    subprocess.run(args, cwd=root, env=env, check=True, capture_output=True, text=True)
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, env=env, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "scanner(*tools): the test runs the named pinned native scanners")


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Scanner tests need the pinned binaries: skipped locally, required in CI.

    ``scripts/install_scanners.sh`` installs them; under CI a missing scanner is
    left to fail the test, never skipped.
    """
    for marker in item.iter_markers("scanner"):
        for tool in marker.args:
            try:
                resolve(tool)
            except CannotRun as exc:
                if not RUNNER_IN_CI:
                    pytest.skip(f"{exc}; run scripts/bootstrap.sh --scanners")


@pytest.fixture(autouse=True)
def ci_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate runs fail closed without inheriting the caller's revision range.

    Pre-commit exports these refs for the real repository. They cannot resolve
    in the throwaway repositories used by these tests, and can change which
    fixture commits a differential gate examines.
    """
    monkeypatch.delenv("CX_DUP_BASE_REF", raising=False)
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    monkeypatch.setenv("CI", "true")


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    """A committed fixture: pyproject with a ``pkg`` package and the fleet KISS config."""
    fixture = Repo(tmp_path / "repo")
    fixture.root.mkdir()
    fixture.git("init", "-q", "-b", "main")
    fixture.commit(
        {
            "pyproject.toml": PYPROJECT,
            ".config/kiss.toml": (HOOK_REPOSITORY / ".config" / "kiss.toml").read_text(encoding="utf-8"),
            "pkg/__init__.py": '"""Fixture package."""\n',
        },
        "base",
    )
    return fixture


def branchy(name: str, branches: int) -> str:
    """A function with ``branches`` early returns: cyclomatic ``branches + 1``."""
    body = "".join(f"    if value == {index}:\n        return {index}\n" for index in range(branches))
    return f"def {name}(value):\n{body}    return -1\n"
