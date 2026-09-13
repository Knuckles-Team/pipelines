"""complexity-census: every tracked function under the census paths, at an absolute zero.

The staged gate is diff-scoped so pre-existing debt elsewhere cannot block an
unrelated commit; the census is where that debt stays visible. It measures
every tracked cccc-supported file under ``[tool.pipelines_hooks.complexity]
census_paths`` (default: the declared packages), prints the terms-of-acceptance
split, and fails while the real backlog is above zero. No baseline, no
allowlist: accepted-by-rule functions are counted and printed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.complexity import cccc, terms
from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tools import verified
from pipelines_hooks.core.tracked import tracked_paths


def census_paths(root: Path) -> tuple[str, ...]:
    """Configured census paths, defaulting to the declared packages."""
    config = load_config(root)
    section = config.section("complexity")
    if "census_paths" in section:
        return string_tuple(section["census_paths"], "complexity.census_paths")
    return config.required_packages()


def census_files(root: Path, paths: tuple[str, ...]) -> list[str]:
    """Tracked cccc-supported files below ``paths``; an empty universe fails closed."""
    files = sorted(
        path
        for path in tracked_paths(root, paths)
        if Path(path).suffix.lower() in cccc.SUPPORTED_SUFFIXES
    )
    if not files:
        raise CannotRun(f"no tracked cccc-supported file under {', '.join(paths)}")
    return files


def measured_rows(root: Path) -> list[tuple[Path, cccc.Row]]:
    """Every function under the census paths, with its absolute file path."""
    files = census_files(root, census_paths(root))
    document = cccc.run(verified("cccc"), files, cwd=root)
    print(f"complexity census: {len(files)} tracked file(s)")
    return [(root / path, row) for path, row in cccc.file_rows(document)]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="complexity-census", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    rows = measured_rows(root)
    over, cognitive, counts = terms.tally(rows)
    backlog = terms.report(len(rows), len(over), cognitive=cognitive, counts=counts)
    for path, row in terms.unaccepted(over):
        print(f"  OVER {path.relative_to(root)}:{row.line} {row.name} cyc={row.cyclomatic} cog={row.cognitive}")
    if backlog:
        print(f"complexity census: FAIL: {backlog} function(s) over a cap outside the terms")
        return 1
    print("complexity census: OK: zero functions over a cap outside the terms")
    return 0
