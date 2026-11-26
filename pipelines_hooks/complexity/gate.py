"""complexity: the one shared complexity gate, configured by ``[tool.complexity]`` in pyproject.toml.

It always runs the diff-scoped staged check (no new or worsened function over cyclomatic 10 /
cognitive 15). With ``census = true`` it also runs the absolute census over ``census_paths``
(default: every declared package). The caps are not configurable: a ``max_*`` key, or any key the
gate does not know, is refused, so a repository cannot raise a threshold through its table.
"""

from __future__ import annotations

import argparse
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipelines_hooks.complexity import census, staged
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root

KEYS = frozenset({"census", "census_paths"})


def table(root: Path) -> Mapping[str, Any]:
    """The validated ``[tool.complexity]`` table (empty when the repository declares none)."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return {}
    try:
        value = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}).get("complexity", {})
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"complexity: cannot read {pyproject}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise CannotRun("complexity: [tool.complexity] must be a table")
    unknown = sorted(set(value) - KEYS)
    if unknown:
        raise CannotRun(f"complexity: [tool.complexity] has unknown key(s): {', '.join(unknown)}; the caps are fixed")
    if not isinstance(value.get("census", False), bool):
        raise CannotRun("complexity: [tool.complexity] census must be true or false")
    return value


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="complexity", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    settings = table(root)
    status = staged.main(["--root", str(root)])
    if settings.get("census"):
        status = max(status, census.main(["--root", str(root)]))
    return status
