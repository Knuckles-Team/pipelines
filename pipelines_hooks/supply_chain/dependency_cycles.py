"""Dependency-group cycle detection for the supply-chain gate.

The resolver lock records packages, but it does not preserve the dependency
group relationships declared by a project.  This module builds that small
group graph directly from ``pyproject.toml`` so cycles are reported before a
release can land.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.supply_chain.finding import Finding, Source


@dataclass(frozen=True)
class DependencyEdge:
    """One directed relationship between two declared dependency groups."""

    source_group: str
    target_group: str
    via: str


@dataclass(frozen=True)
class DependencyLoop:
    """One strongly connected dependency-group component."""

    members: tuple[str, ...]


@dataclass(frozen=True)
class InvalidDependencyGroup:
    """One located-invalid ``include-group`` reference.

    Invalid references are kept out of the graph: reporting them separately
    prevents an unknown target from becoming an invented node while still
    making the manifest fail closed through the supply-chain gate.
    """

    source_group: str
    value: object
    reason: str
    include_index: int


INVALID_GROUP_RULE = "SC-DEP-006"


def _table(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    return value if isinstance(value, dict) else {}


def _project(document: dict[str, Any]) -> dict[str, Any]:
    return _table(document, "project")


def _group_values(document: dict[str, Any]) -> list[tuple[str, object]]:
    """Return the root, optional-extra and dependency-group declarations."""
    project = _project(document)
    declarations: list[tuple[str, object]] = [("root", project.get("dependencies", []))]
    optional = _table(project, "optional-dependencies")
    declarations.extend((name, value) for name, value in optional.items() if isinstance(name, str))
    development = _table(document, "dependency-groups")
    declarations.extend((name, value) for name, value in development.items() if isinstance(name, str))
    return declarations


def _group_names(declarations: Iterable[tuple[str, object]]) -> set[str]:
    names = {name for name, _ in declarations}
    return names


def _normalise_name(value: str) -> str:
    """Apply the package/extra spelling normalisation used by TOML metadata."""
    return re.sub(r"[-_.]+", "-", value).casefold()


def _known_group(value: str, groups: set[str]) -> str | None:
    if value in groups:
        return value
    folded = _normalise_name(value)
    return next((group for group in groups if _normalise_name(group) == folded), None)


def _items(value: object) -> Iterable[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, (str, dict)):
        return (value,)
    return ()


def _include_groups(item: object) -> Iterable[str]:
    if not isinstance(item, dict):
        return ()
    included = item.get("include-group")
    if isinstance(included, str):
        return (included,)
    return ()


def invalid_dependency_groups(document: dict[str, Any]) -> list[InvalidDependencyGroup]:
    """Return malformed or undeclared include references without graph nodes."""
    declarations = _group_values(document)
    groups = _group_names(declarations)
    issues: list[InvalidDependencyGroup] = []
    include_index = 0
    for source_group, values in declarations:
        for item in _items(values):
            if not isinstance(item, dict) or "include-group" not in item:
                continue
            value = item["include-group"]
            current_index = include_index
            include_index += 1
            if not isinstance(value, str):
                issues.append(
                    InvalidDependencyGroup(
                        source_group,
                        value,
                        f"malformed include-group reference {value!r} (expected a string)",
                        current_index,
                    )
                )
                continue
            if not value.strip() or _known_group(value, groups) is None:
                issues.append(
                    InvalidDependencyGroup(
                        source_group,
                        value,
                        f"unknown include-group target {value!r}",
                        current_index,
                    )
                )
    return issues


_SELF_EXTRA_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s*\[([^]]+)\]")


def _project_extras(item: object, project_name: str | None) -> Iterable[str]:
    if project_name is None or not isinstance(item, str):
        return ()
    match = _SELF_EXTRA_RE.match(item)
    if match is None or _normalise_name(match.group(1)) != _normalise_name(project_name):
        return ()
    return (extra.strip() for extra in match.group(2).split(",") if extra.strip())


def group_edges(document: dict[str, Any]) -> list[DependencyEdge]:
    """Build edges from group includes and references to the project's extras.

    ``include-group`` is represented by a PEP 735 inline table.  A dependency
    such as ``project-name[lint]`` is an edge from the declaring group to the
    named optional extra.  Unknown or malformed include targets are omitted
    from the graph and reported by :func:`dependency_group_findings` so an
    invalid manifest cannot invent a node while silently passing the gate.
    """
    declarations = _group_values(document)
    groups = _group_names(declarations)
    project = _project(document)
    optional = _table(project, "optional-dependencies")
    extra_groups = {name for name in optional if isinstance(name, str)}
    project_name = project.get("name")
    project_name = project_name if isinstance(project_name, str) else None
    edges: list[DependencyEdge] = []
    for source_group, values in declarations:
        for item in _items(values):
            for target_name in _include_groups(item):
                target_group = _known_group(target_name, groups)
                if target_group is not None:
                    edges.append(DependencyEdge(source_group, target_group, f"include-group:{target_name}"))
            for target_name in _project_extras(item, project_name):
                target_group = _known_group(target_name, extra_groups)
                if target_group is not None:
                    edges.append(DependencyEdge(source_group, target_group, str(item)))
    return edges


def dependency_group_findings(label: str, text: str, document: dict[str, Any]) -> list[Finding]:
    """Locate malformed or undeclared include references in the manifest."""
    source = Source(label, "pyproject.toml", text)
    include_offsets = [match.start() for match in re.finditer(r"(?:['\"]?include-group['\"]?)\s*=", text)]
    findings: list[Finding] = []
    for issue in invalid_dependency_groups(document):
        offset = (
            include_offsets[issue.include_index]
            if issue.include_index < len(include_offsets)
            else _group_offset(text, issue.source_group)
        )
        findings.append(
            source.at_offset(
                offset,
                rule=INVALID_GROUP_RULE,
                message=f"dependency group {issue.source_group!r} has {issue.reason}",
            )
        )
    return findings


def find_loops(edges: Iterable[DependencyEdge]) -> list[DependencyLoop]:
    """Return sorted strongly connected components, including self-loops."""
    graph: nx.DiGraph = nx.DiGraph()
    for edge in edges:
        graph.add_edge(edge.source_group, edge.target_group)
    loops = [
        DependencyLoop(tuple(sorted(component)))
        for component in nx.strongly_connected_components(graph)
        if len(component) > 1 or any(graph.has_edge(member, member) for member in component)
    ]
    return sorted(loops, key=lambda loop: (-len(loop.members), loop.members))


def _group_offset(text: str, group: str) -> int:
    """Locate a declaration line for evidence attached to a loop finding."""
    if group == "root":
        match = re.search(r"(?m)^\s*\[project\]\s*$", text)
    else:
        match = re.search(rf"(?m)^\s*{re.escape(group)}\s*=", text)
    return match.start() if match is not None else 0


def loop_findings(label: str, pyproject: Path, reader: Callable[[Path], str]) -> list[Finding]:
    """Return one located ``SC-DEP-LOOP`` finding per manifest cycle.

    Parsing failures are intentionally left to ``_pyproject_findings`` so its
    existing typed ``SC-DEP-004`` finding remains the single parse diagnostic.
    """
    try:
        text = reader(pyproject)
        document = tomllib.loads(text)
    except (CannotRun, tomllib.TOMLDecodeError):
        return []
    source = Source(label, "pyproject.toml", text)
    findings = dependency_group_findings(label, text, document)
    for loop in find_loops(group_edges(document)):
        members = ", ".join(loop.members)
        offset = min((_group_offset(text, member) for member in loop.members), default=0)
        findings.append(
            source.at_offset(
                offset,
                rule="SC-DEP-LOOP",
                message=f"dependency group loop: {members}",
            )
        )
    return findings
