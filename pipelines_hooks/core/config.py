"""The per-repository ``[tool.pipelines_hooks]`` table.

Every repository-specific input of a shared gate lives here, in the consuming
repository's own ``pyproject.toml``; the gate implementations are never edited
per repository. Validation is strict: an unknown section or key is a
configuration error (exit 2), never silently ignored, so a typo cannot quietly
narrow what a gate measures.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun

#: Every section a gate may read, and the keys it accepts.
SECTIONS: dict[str, frozenset[str]] = {
    "complexity": frozenset({"census_paths"}),
    "kiss": frozenset({"paths"}),
    "env_sprawl": frozenset({"allow_files"}),
    "stdout_writes": frozenset({"served_paths"}),
    "stubs": frozenset({"declared_seams"}),
    "ci_replica": frozenset({"workflows", "build_affecting"}),
}
_TOP_LEVEL = frozenset({"packages"}) | frozenset(SECTIONS)


@dataclass(frozen=True)
class RepoConfig:
    """A validated ``[tool.pipelines_hooks]`` table for one repository."""

    root: Path
    table: Mapping[str, Any] = field(default_factory=dict)

    def section(self, name: str) -> Mapping[str, Any]:
        """One validated section (empty when absent)."""
        value = self.table.get(name, {})
        if not isinstance(value, Mapping):
            raise CannotRun(f"[tool.pipelines_hooks.{name}] must be a table")
        unknown = sorted(set(value) - SECTIONS[name])
        if unknown:
            raise CannotRun(
                f"[tool.pipelines_hooks.{name}] has unknown key(s): {', '.join(unknown)}"
            )
        return value

    def packages(self) -> tuple[str, ...]:
        """The repository's importable package directories."""
        return string_tuple(self.table.get("packages", []), "packages")

    def required_packages(self) -> tuple[str, ...]:
        """Packages, failing closed when none are declared."""
        packages = self.packages()
        if not packages:
            raise CannotRun("[tool.pipelines_hooks] declares no packages")
        return packages


def string_tuple(value: object, name: str) -> tuple[str, ...]:
    """A list of non-empty strings, without duplicates."""
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise CannotRun(f"[tool.pipelines_hooks] {name} must be a list of strings")
    items = tuple(item.strip() for item in value)
    if len(set(items)) != len(items):
        raise CannotRun(f"[tool.pipelines_hooks] {name} contains duplicates")
    return items


def _read_table(pyproject: Path) -> Mapping[str, Any]:
    try:
        document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {pyproject}: {exc}") from exc
    table = document.get("tool", {}).get("pipelines_hooks", {})
    if not isinstance(table, Mapping):
        raise CannotRun("[tool.pipelines_hooks] must be a table")
    return table


def load_config(root: Path) -> RepoConfig:
    """The repository's validated configuration (empty without a pyproject)."""
    pyproject = root / "pyproject.toml"
    table = _read_table(pyproject) if pyproject.is_file() else {}
    unknown = sorted(set(table) - _TOP_LEVEL)
    if unknown:
        raise CannotRun(f"[tool.pipelines_hooks] has unknown key(s): {', '.join(unknown)}")
    return RepoConfig(root=root, table=table)
