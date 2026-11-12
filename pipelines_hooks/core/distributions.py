"""Distribution identities shared by release and connector gates.

Each logical ecosystem role has exactly one accepted distribution name.
Retired spellings are not recognised anywhere.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType

SDK = "sdk"
MERISTEM = "meristem"
MEDULLA = "medulla"
OVERSTORY = "overstory"
TUIG = "tuig"
AXIL = "axil"

DISTRIBUTIONS = MappingProxyType(
    {
        SDK: "scion-sdk",
        MERISTEM: "meristem",
        MEDULLA: "medulla",
        OVERSTORY: "overstory",
        TUIG: "tuig",
        AXIL: "axil",
    }
)

_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalized(value: str) -> str:
    """Return the PEP 503-like spelling used for comparisons."""
    return re.sub(r"[-_.]+", "-", str(value)).lower()


def requirement_name(value: str) -> str:
    """Extract and normalize a distribution name from a requirement string."""
    match = _REQUIREMENT_NAME.match(str(value))
    return normalized(match.group(1)) if match else ""


def distribution(role: str) -> str:
    """Return the one accepted distribution name for a logical ecosystem role."""
    try:
        return DISTRIBUTIONS[role]
    except KeyError as exc:
        raise ValueError(f"unknown distribution role: {role}") from exc


def is_distribution(value: str, role: str) -> bool:
    """Whether ``value`` is the current distribution name for ``role``."""
    return normalized(value) == distribution(role)


def distribution_for(requirements: Iterable[str], role: str, *, default: str | None = None) -> str:
    """Return the role's distribution name when ``requirements`` declare it.

    Only the current name is recognised; ``default`` is returned when absent.
    """
    current = distribution(role)
    for requirement in requirements:
        if requirement_name(str(requirement)) == current:
            return current
    return normalized(default) if default is not None else current


def project_distribution(project: Mapping[str, object], role: str, *, default: str | None = None) -> str:
    """Find a role distribution in a parsed ``[project]`` table."""
    values: list[str] = []
    dependencies = project.get("dependencies", [])
    if isinstance(dependencies, list | tuple):
        values.extend(str(value) for value in dependencies)
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, Mapping):
        for entries in optional.values():
            if isinstance(entries, list | tuple):
                values.extend(str(value) for value in entries)
    return distribution_for(values, role, default=default)
