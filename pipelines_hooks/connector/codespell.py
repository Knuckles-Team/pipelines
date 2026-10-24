"""connector-codespell: codespell over tracked prose and source with the shared default ignore list."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pipelines_hooks.connector import project
from pipelines_hooks.connector.files import tracked
from pipelines_hooks.core.errors import Unavailable
from pipelines_hooks.core.gitenv import repo_root, sanitized_env

DEFAULT_IGNORE = Path(__file__).resolve().parent / "defaults" / "codespellignore"
EXCLUDE = re.compile(r"^(tests/|test/|scripts/|script/)|lock")
CHUNK = 200


def ignore_words(root: Path) -> list[str]:
    """The shared default words plus the connector's ``[tool.pipelines.codespell] ignore_words``."""
    words = [
        w.strip()
        for w in DEFAULT_IGNORE.read_text(encoding="utf-8").splitlines()
        if w.strip() and not w.startswith("#")
    ]
    extra = project.load(root).get("tool", {}).get("pipelines", {}).get("codespell", {}).get("ignore_words", [])
    return sorted(set(words) | {str(w) for w in extra})


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-codespell", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    files = [f for f in tracked(root) if not EXCLUDE.search(f) and (root / f).is_file()]
    probe = subprocess.run([sys.executable, "-m", "codespell_lib", "--version"], capture_output=True, check=False)
    if probe.returncode != 0:
        raise Unavailable("codespell is not installed in the hook environment", remedy="pip install codespell")
    with tempfile.TemporaryDirectory() as scratch:
        words = Path(scratch) / "ignore-words"
        words.write_text("\n".join(ignore_words(root)) + "\n", encoding="utf-8")
        status = 0
        for start in range(0, len(files), CHUNK):
            run = subprocess.run(
                [sys.executable, "-m", "codespell_lib", f"--ignore-words={words}", *files[start : start + CHUNK]],
                cwd=root,
                env=sanitized_env(),
                check=False,
            )
            status = status or run.returncode
    return 1 if status else 0
