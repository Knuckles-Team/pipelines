"""Distribution identities shared by release and connector gates.

The ecosystem is changing a handful of *distribution* names while keeping
Python import paths, repository identities, and ontology identifiers stable.
During the transition every gate must accept both spellings.  The old spelling
remains the default so an existing consumer is never rewritten accidentally;
callers that are deliberately migrating can request the new spelling.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType

SDK = "sdk"
MERISTEM = "meristem"
MEDULLA = "medulla"
MEDULLA_STEM = "medulla-stem"
OVERSTORY = "overstory"
TUIG = "tuig"
AXIL = "axil"

OLD_DISTRIBUTIONS = MappingProxyType(
    {
        SDK: "agent-connector-sdk",
        MERISTEM: "agent-utilities",
        MEDULLA: "epistemic-graph",
        MEDULLA_STEM: "epistemic-graph-server",
        OVERSTORY: "agent-webui",
        TUIG: "agent-terminal-ui",
        AXIL: "geniusbot",
    }
)
NEW_DISTRIBUTIONS = MappingProxyType(
    {
        SDK: "scion-sdk",
        MERISTEM: "meristem",
        MEDULLA: "medulla",
        MEDULLA_STEM: "medulla-stem",
        OVERSTORY: "overstory",
        TUIG: "tuig",
        AXIL: "axil",
    }
)
DISTRIBUTION_ALIASES: Mapping[str, frozenset[str]] = MappingProxyType(
    {role: frozenset((old, NEW_DISTRIBUTIONS[role])) for role, old in OLD_DISTRIBUTIONS.items()}
)

_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalized(value: str) -> str:
    """Return the PEP 503-like spelling used for comparisons."""
    return re.sub(r"[-_.]+", "-", str(value)).lower()


def requirement_name(value: str) -> str:
    """Extract and normalize a distribution name from a requirement string."""
    match = _REQUIREMENT_NAME.match(str(value))
    return normalized(match.group(1)) if match else ""


def aliases(role: str) -> frozenset[str]:
    """Return the accepted old/new names for a logical ecosystem role."""
    try:
        return DISTRIBUTION_ALIASES[role]
    except KeyError as exc:
        raise ValueError(f"unknown distribution role: {role}") from exc


def is_distribution(value: str, role: str) -> bool:
    """Whether ``value`` is either accepted spelling for ``role``."""
    return normalized(value) in aliases(role)


def distribution_for(requirements: Iterable[str], role: str, *, default: str | None = None) -> str:
    """Find the first role distribution in ``requirements``.

    The returned spelling is normalized but preserves whether the caller used
    the old or new alias.  This is the behavior generic codemods need when
    raising a version floor without performing a name migration.
    """
    accepted = aliases(role)
    for requirement in requirements:
        name = requirement_name(str(requirement))
        if name in accepted:
            return name
    if default is not None:
        return normalized(default)
    return OLD_DISTRIBUTIONS[role]


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


def migration_distribution(role: str) -> str:
    """Return the new spelling used by an explicitly requested migration."""
    try:
        return NEW_DISTRIBUTIONS[role]
    except KeyError as exc:
        raise ValueError(f"unknown distribution role: {role}") from exc
