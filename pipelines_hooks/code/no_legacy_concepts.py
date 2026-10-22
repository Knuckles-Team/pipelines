"""Reject numeric-pillar concept markers in tracked source and documentation."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths

_LEGACY_RE = re.compile(r"CONCEPT:[A-Z]+-[0-9]")
_EXT = {".py", ".rs", ".md"}
_SKIP = {"__pycache__", ".git", ".venv", "node_modules", "target", "build", "dist"}
# Preserve the original checker and historical/generated registry exclusions.
_HISTORY = {
    "check_no_legacy_markers.py",
    "CHANGELOG.md",
    "concept_map.md",
    "concepts.yaml",
    "concept_reservations.yaml",
}


def scan(root: Path) -> list[str]:
    """Scan one target using its own tracked index, never a hook's foreign index."""
    root = root.resolve()
    repository = repo_root(root)
    hits: list[str] = []
    for relative in tracked_paths(repository, preserve_index=False):
        path = repository / relative
        if not path.is_relative_to(root):
            continue
        if path.suffix not in _EXT or any(part in _SKIP for part in path.parts) or path.name in _HISTORY:
            continue
        # A tracked deletion is not surviving source.
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CannotRun(f"cannot read {path}: {exc}") from exc
        for number, line in enumerate(text.splitlines(), 1):
            if _LEGACY_RE.search(line):
                hits.append(f"{path.relative_to(root)}:{number}: {line.strip()[:100]}")
    return hits


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, help="repository or subtree to scan")
    args = parser.parse_args(argv)
    roots = ([args.root] if args.root else []) + args.roots or [Path.cwd()]
    hits = [hit for root in roots for hit in scan(root)]
    if hits:
        print(f"FAIL: {len(hits)} legacy concept marker(s) survive the cutover:")
        for hit in hits[:60]:
            print("  " + hit)
        if len(hits) > 60:
            print(f"  … and {len(hits) - 60} more")
        return 1
    print("OK: no legacy CONCEPT: markers remain.")
    return 0
