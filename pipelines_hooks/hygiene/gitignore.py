"""gitignore-convergence: every repository ignores the fleet-shared REQUIRED set.

1. NEGATIVE: every REQUIRED token appears as its own ``.gitignore`` line; a
   purely presentational leading/trailing ``/`` is ignored (dropping it only
   widens the match, never narrows it).
2. POSITIVE: no ``dist``/``build``/``target`` directory (or a ``-suffixed``
   sibling) is already tracked -- a rule only stops FUTURE adds. The check is
   anchored to a path SEGMENT, so ``build.rs`` or ``build_backend.py`` are fine.

Each REQUIRED entry exists because one fleet repository was burned by exactly
what it excludes; convergence is the point, so a repository never narrows it.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths

REQUIRED = frozenset(
    {"dist/", "dist-*/", "sdist/", "build/", "target/", "target-*/", ".venv/", ".mypy_cache/", ".pytest_cache/",
     ".ruff_cache/", ".hypothesis/", ".pytest_tmp/", "node_modules/", ".kissconfig", "reports/", "scratch/"}
)
_TRACKED_BUILD_OUTPUT_RE = re.compile(r"^(dist|build|target)(-[^/]*)?/")


def gitignore_tokens(root: Path) -> set[str]:
    path = root / ".gitignore"
    if not path.is_file():
        return set()
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return {line.strip("/") for line in lines if line and not line.startswith("#")}


def problems(root: Path) -> list[str]:
    tokens = gitignore_tokens(root)
    missing = sorted(token for token in REQUIRED if token.strip("/") not in tokens)
    tracked = sorted(path for path in tracked_paths(root) if _TRACKED_BUILD_OUTPUT_RE.match(path))
    found = []
    if missing:
        found.append("Missing from .gitignore (fleet-shared REQUIRED set):\n" + "\n".join(f"    {m}" for m in missing))
    if tracked:
        found.append("Build-output paths are TRACKED (delete them; a rule cannot un-track):\n" + "\n".join(f"    {p}" for p in tracked))
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gitignore-convergence", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    found = problems(repo_root(parser.parse_args(argv).root))
    if not found:
        print(f"gitignore convergence: clean ({len(REQUIRED)} required entries, 0 tracked build-output paths)")
        return 0
    print("FAIL: .gitignore convergence violations.\n")
    print("\n\n".join(found))
    return 1
