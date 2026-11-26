"""Read one ``[tool.pipelines.<name>]`` table of a repository's ``pyproject.toml``."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun


def table(root: Path, name: str) -> dict:
    """The declared table, or an empty dict when the repository declares none."""
    path = root / "pyproject.toml"
    if not path.is_file():
        return {}
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise CannotRun("malformed pyproject.toml") from exc
    return document.get("tool", {}).get("pipelines", {}).get(name, {})
