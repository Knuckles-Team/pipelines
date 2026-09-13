"""Which paths the KISS gates own in a repository."""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.paths import under_any
from pipelines_hooks.kiss.runner import LANGUAGES


def kiss_paths(root: Path) -> tuple[str, ...]:
    """``[tool.pipelines_hooks.kiss] paths``, defaulting to the declared packages."""
    config = load_config(root)
    section = config.section("kiss")
    if "paths" in section:
        return string_tuple(section["paths"], "kiss.paths")
    return config.required_packages()


def in_scope(path: str, paths: tuple[str, ...]) -> bool:
    """A Python or Rust source file below one of the KISS paths."""
    return Path(path).suffix in LANGUAGES and under_any(path, paths)
