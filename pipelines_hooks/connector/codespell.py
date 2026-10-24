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


def _table(root: Path) -> dict[str, object]:
    return dict(project.load(root).get("tool", {}).get("pipelines", {}).get("codespell", {}))


def extra_excludes(root: Path) -> list[str]:
    """The connector's own ``[tool.pipelines.codespell] exclude`` paths (a file or a directory prefix)."""
    return [str(p).rstrip("/") for p in _table(root).get("exclude", [])]  # type: ignore[attr-defined]


def excluded(path: str, extra: list[str]) -> bool:
    """True when the central scope or one of the connector's own ``exclude`` paths leaves ``path`` out."""
    return bool(EXCLUDE.search(path)) or any(path == e or path.startswith(e + "/") for e in extra)


def ignore_words(root: Path) -> list[str]:
    """The shared default words plus the connector's ``[tool.pipelines.codespell] ignore_words``."""
    words = [
        w.strip()
        for w in DEFAULT_IGNORE.read_text(encoding="utf-8").splitlines()
        if w.strip() and not w.startswith("#")
    ]
    extra = _table(root).get("ignore_words", [])
    return sorted(set(words) | {str(w) for w in extra})  # type: ignore[attr-defined]


def findings(root: Path, extra: list[str] | None = None) -> list[str]:
    """The codespell findings (``path:line: word ==> fix``) over tracked files plus ``extra``; none means clean."""
    paths = dict.fromkeys([*tracked(root), *(extra or [])])
    skip = extra_excludes(root)
    files = [f for f in paths if not excluded(f, skip) and (root / f).is_file()]
    probe = subprocess.run([sys.executable, "-m", "codespell_lib", "--version"], capture_output=True, check=False)
    if probe.returncode != 0:
        raise Unavailable("codespell is not installed in the hook environment", remedy="pip install codespell")
    out: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        words = Path(scratch) / "ignore-words"
        words.write_text("\n".join(ignore_words(root)) + "\n", encoding="utf-8")
        for start in range(0, len(files), CHUNK):
            run = subprocess.run(
                [sys.executable, "-m", "codespell_lib", f"--ignore-words={words}", *files[start : start + CHUNK]],
                cwd=root,
                env=sanitized_env(),
                check=False,
                capture_output=True,
                text=True,
            )
            out += [ln for ln in run.stdout.splitlines() if ln.strip()]
            if run.returncode and not run.stdout.strip():
                out.append(f"codespell: exit {run.returncode}: {run.stderr.strip()[-300:]}")
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-codespell", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    lines = findings(repo_root(parser.parse_args(argv).root))
    for line in lines:
        print(line)
    return 1 if lines else 0
