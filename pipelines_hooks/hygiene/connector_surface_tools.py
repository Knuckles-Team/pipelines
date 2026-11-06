"""Tools and data resources of a connector surface, read without importing it.

A connector serves one typed tool per upstream operation. The Scion SDK
derives those tools from the client class a ``Connector(api=...)`` declaration
names, or a module registers them with ``@<server>.tool``. A tool that routes
an ``action`` argument to several operations is a condensed tool, and so is any
registration that passes ``action_dispatch=True``.

A connector serves at least one data resource. It declares its sources with
``source_meta(...)`` (normally in ``connector_sources.py``) or registers a
resource with ``@<server>.resource``.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

#: Parameter names that route one tool to several operations.
ROUTING_PARAMETERS = frozenset({"action"})
_TOOL_REGISTRARS = frozenset({"register_tool_surface", "register_method_tools"})


@dataclass
class Surface:
    """Static facts about the tools and resources of one package."""

    decorated_tools: list[str] = field(default_factory=list)
    derived_tools: bool = False
    routed_tools: list[str] = field(default_factory=list)
    action_dispatch: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    api_class: str | None = None
    tool_prefix: str | None = None
    classes: dict[str, tuple[list[str], list[str]]] = field(default_factory=dict)


def _decorator_kind(decorator: ast.expr) -> tuple[str, str | None]:
    """``("tool" | "resource" | "", explicit name)`` for one decorator."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    kind = getattr(target, "attr", "")
    name = None
    if isinstance(decorator, ast.Call):
        for keyword in decorator.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                name = str(keyword.value.value)
    return (kind if kind in {"tool", "resource"} else ""), name


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = node.args
    return {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}


def _scan_function(node: ast.FunctionDef | ast.AsyncFunctionDef, rel: str, surface: Surface) -> None:
    for decorator in node.decorator_list:
        kind, name = _decorator_kind(decorator)
        label = name or node.name
        if kind == "tool":
            surface.decorated_tools.append(label)
            if _parameters(node) & ROUTING_PARAMETERS:
                surface.routed_tools.append(f"{label} ({rel})")
        elif kind == "resource":
            surface.resources.append(f"{label} ({rel})")


def _scan_call(node: ast.Call, rel: str, surface: Surface) -> None:
    name = getattr(node.func, "id", getattr(node.func, "attr", ""))
    keywords = {k.arg: k.value for k in node.keywords if k.arg}
    if (name == "Connector" and "api" in keywords) or name in _TOOL_REGISTRARS:
        surface.derived_tools = True
        api = keywords.get("api") or keywords.get("client_cls")
        if isinstance(api, (ast.Name, ast.Attribute)):
            surface.api_class = getattr(api, "id", getattr(api, "attr", None))
        prefix = keywords.get("tool_prefix")
        if isinstance(prefix, ast.Constant) and isinstance(prefix.value, str):
            surface.tool_prefix = prefix.value
    if name == "source_meta":
        surface.resources.append(f"source_meta ({rel})")
    flag = keywords.get("action_dispatch")
    if isinstance(flag, ast.Constant) and flag.value is True:
        surface.action_dispatch.append(rel)


def _scan_class(node: ast.ClassDef, surface: Surface) -> None:
    bases = [getattr(b, "id", getattr(b, "attr", "")) for b in node.bases]
    methods = [
        item.name
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_")
    ]
    surface.classes.setdefault(node.name, (bases, methods))


def _methods(surface: Surface, name: str, seen: set[str]) -> set[str]:
    """Public methods of ``name`` and its package bases; infrastructure ``*Base*`` classes add none."""
    if name in seen or name not in surface.classes:
        return set()
    seen.add(name)
    bases, methods = surface.classes[name]
    found = set() if "Base" in name else set(methods)
    for base in bases:
        found |= _methods(surface, base, seen)
    return found


_SUFFIXES = ("-mcp", "-agent", "-api", "-server")


def tool_names(surface: Surface, connector: str) -> list[str]:
    """The tool names the package serves, as far as a static read can tell.

    Decorated tools keep their names. Derived tools are ``<prefix>_<method>`` for
    each public method of the declared client class and its package bases.
    """
    names = set(surface.decorated_tools)
    if surface.api_class:
        prefix = surface.tool_prefix
        if prefix is None:
            prefix = connector
            for suffix in _SUFFIXES:
                prefix = prefix.removesuffix(suffix)
            prefix = prefix.replace("-", "_")
        for method in _methods(surface, surface.api_class, set()):
            names.add(method if method.startswith(prefix + "_") else f"{prefix}_{method}")
    return sorted(names)


def scan(sources: Iterable[Path], root: Path) -> Surface:
    """The tool and resource facts of ``sources`` (paths under ``root``)."""
    surface = Surface()
    for path in sources:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                _scan_class(node, surface)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _scan_function(node, rel, surface)
            elif isinstance(node, ast.Call):
                _scan_call(node, rel, surface)
    surface.decorated_tools.sort()
    surface.routed_tools.sort()
    surface.resources.sort()
    surface.action_dispatch.sort()
    return surface


def tool_gaps(surface: Surface) -> list[str]:
    """One typed tool per upstream operation, and nothing condensed into action routing."""
    gaps = []
    if not surface.decorated_tools and not surface.derived_tools:
        gaps.append("tools: no tool registered (no Connector(api=...) and no @<server>.tool)")
    gaps.extend(f"tools: action-routed tool {name}" for name in surface.routed_tools)
    gaps.extend(f"tools: action_dispatch=True in {rel}" for rel in surface.action_dispatch)
    return gaps


def resource_gaps(surface: Surface) -> list[str]:
    """At least one declared data resource."""
    if surface.resources:
        return []
    return ["resources: no data resource (no source_meta(...) and no @<server>.resource)"]
