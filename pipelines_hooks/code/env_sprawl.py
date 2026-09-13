"""env-sprawl: package code reads the environment only in its declared configuration module.

Every bare read of a literal variable name -- through ``os.environ.get``,
``os.getenv`` or an ``os.environ`` subscript -- outside
``[tool.pipelines_hooks.env_sprawl] allow_files`` fails, at an absolute maximum
of zero. A subscript assignment is cross-process signalling, not a read.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import skipped, tracked_or_walked

PATTERN_GET = re.compile(r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""")
PATTERN_SUBSCRIPT = re.compile(r"""os\.environ\[\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\](?!\s*=[^=])""")


def bare_reads(source: str) -> set[str]:
    """Every variable name read directly from the environment in ``source``."""
    return {m.group(1) for pattern in (PATTERN_GET, PATTERN_SUBSCRIPT) for m in pattern.finditer(source)}


def scan(root: Path) -> list[tuple[str, str]]:
    config = load_config(root)
    allowed = set(string_tuple(config.section("env_sprawl").get("allow_files", []), "env_sprawl.allow_files"))
    paths = [p for package in config.required_packages() for p in tracked_or_walked(root / package, ("*.py",), root=root)]
    found = set()
    for path in paths:
        rel = path.relative_to(root).as_posix()
        if not skipped(Path(rel)) and rel not in allowed:
            found.update((rel, key) for key in bare_reads(path.read_text(encoding="utf-8", errors="replace")))
    return sorted(found)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="env-sprawl", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    found = scan(repo_root(parser.parse_args(argv).root))
    print(f"env-sprawl bare reads found: {len(found)} (max allowed: 0)")
    for rel, key in found:
        print(f"  {rel}: {key}")
    if found:
        print("Read the variable through the package's declared configuration module instead.")
        return 1
    return 0
