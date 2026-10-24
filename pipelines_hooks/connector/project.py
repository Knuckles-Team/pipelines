"""Read a connector's ``pyproject.toml`` and its ``[tool.pipelines.*]`` tables."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun

CONTAINER_KEYS = frozenset(
    {
        "host",
        "port",
        "uid",
        "home",
        "entrypoints",
        "sdist_deps",
        "builder_apt",
        "runtime_apt",
        "runtime_copies",
        "stage_copies",
        "extra_stages",
        "extra_runtime_stages",
        "debug_apt",
        "debug_extras",
        "compose_env",
    }
)


def load(root: Path) -> dict[str, Any]:
    """The parsed ``pyproject.toml`` of the connector at ``root``."""
    path = root / "pyproject.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {path}: {exc}") from exc


def container_table(pyproject: dict[str, Any]) -> dict[str, Any]:
    """The ``[tool.pipelines.container]`` table; an unknown key is refused, never ignored."""
    table = pyproject.get("tool", {}).get("pipelines", {}).get("container", {})
    unknown = sorted(set(table) - CONTAINER_KEYS)
    if unknown:
        raise CannotRun(f"[tool.pipelines.container] has unknown keys: {', '.join(unknown)}")
    return dict(table)


def package_dir(root: Path, pyproject: dict[str, Any]) -> Path:
    """The connector package directory: the connector entry point's module, else the project name."""
    points = pyproject.get("project", {}).get("entry-points", {}).get("agent_connector_sdk.connector", {})
    module = next((str(value).split(":")[0].split(".")[0] for value in points.values()), "")
    module = module or str(pyproject.get("project", {}).get("name", "")).replace("-", "_")
    return root / module
