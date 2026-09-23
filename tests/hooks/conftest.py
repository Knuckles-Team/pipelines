"""Throwaway git repositories and in-process gate runs for the shared-hook tests.

Every gate test plants a violation and proves the gate fires (exit 1), then
proves it passes on a clean fixture (exit 0). Gates run the real pinned
scanners; nothing is mocked except the OSV network client.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.cli import run_gate
from pipelines_hooks.core.gitenv import sanitized_env

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
