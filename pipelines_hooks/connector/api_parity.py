"""connector-api-parity: every public API client method is reachable from an MCP tool, measured against a baseline.

Replaces the per-repository ``scripts/verify_api_integration.py`` (47 copies, about 35 drifted variants, each with
an embedded baseline table for the whole fleet). The check parses ``api_client*.py`` (public methods of classes
whose name holds ``api`` or ``client``) and ``mcp_server.py`` plus its sibling ``mcp/*.py`` registrars (functions
decorated ``.tool``, or named with a configured prefix), and counts the methods a tool calls through ``client``,
``api`` or ``self``, including a ``resolve_action(.., <NAME>_ACTIONS)`` catalog dispatched with ``getattr``.

Per-repository values live in ``[tool.pipelines.api_integration]``:

* ``baseline`` (float, default 0.0): coverage below it fails; coverage below 100 always prints the unmapped methods;
* ``tool_prefixes`` (list of strings, default empty): function-name prefixes that mark an undecorated tool.

A repository with no ``api_client*.py`` or no ``mcp_server.py`` passes silently.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Any

from pipelines_hooks.connector import project
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root

KEYS = frozenset({"baseline", "tool_prefixes"})
TOLERANCE = 0.05
SKIP_PARTS = ("site-packages", "node_modules")


def table(pyproject: dict[str, Any]) -> dict[str, Any]:
    """The ``[tool.pipelines.api_integration]`` table; an unknown key or a wrong type is refused."""
    raw = pyproject.get("tool", {}).get("pipelines", {}).get("api_integration", {})
    unknown = sorted(set(raw) - KEYS)
    if unknown:
        raise CannotRun(f"[tool.pipelines.api_integration] has unknown keys: {', '.join(unknown)}")
    baseline = raw.get("baseline", 0.0)
    if isinstance(baseline, bool) or not isinstance(baseline, int | float) or not 0 <= baseline <= 100:
        raise CannotRun("[tool.pipelines.api_integration] baseline must be a number from 0 to 100")
    prefixes = raw.get("tool_prefixes", [])
    if not isinstance(prefixes, list) or not all(isinstance(p, str) for p in prefixes):
        raise CannotRun("[tool.pipelines.api_integration] tool_prefixes must be a list of strings")
    return {"baseline": float(baseline), "tool_prefixes": tuple(prefixes)}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def api_methods(paths: list[Path]) -> set[str]:
    """Public methods of every ``*api*`` / ``*client*`` class, minus ``authenticate``."""
    methods: set[str] = set()
    for path in sorted(paths):
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.ClassDef) and ("api" in node.name.lower() or "client" in node.name.lower()):
                methods.update(
                    item.name
                    for item in node.body
                    if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
                    and not item.name.startswith("_")
                    and item.name != "authenticate"
                )
    return methods


def _is_tool(node: ast.FunctionDef | ast.AsyncFunctionDef, prefixes: tuple[str, ...]) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == "tool":
            return True
    return bool(prefixes) and node.name.startswith(prefixes)


def _action_catalogs(tree: ast.Module) -> dict[str, set[str]]:
    """Literal module-level ``*_ACTIONS`` tuples, lists and sets of strings."""
    found: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        else:
            continue
        value = node.value
        if not isinstance(value, ast.Tuple | ast.List | ast.Set):
            continue
        items = {e.value for e in value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        found.update({n: items for n in names if n.endswith("_ACTIONS") and len(items) == len(value.elts)})
    return found


def _calls(function: ast.AST) -> tuple[set[str], set[str], bool]:
    """Attributes read on client/api/self, catalogs named by ``resolve_action``, and whether dispatch is dynamic."""
    called: set[str] = set()
    catalogs: set[str] = set()
    dynamic = False
    for node in ast.walk(function):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in ("client", "api", "self"):
                called.add(node.attr)
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name == "getattr" and len(node.args) >= 2 and isinstance(node.args[0], ast.Name):
                if node.args[0].id in ("client", "api"):
                    if isinstance(node.args[1], ast.Constant):
                        called.add(str(node.args[1].value))
                    else:
                        dynamic = True
            if name == "resolve_action" and len(node.args) >= 2 and isinstance(node.args[1], ast.Name):
                catalogs.add(node.args[1].id)
    return called, catalogs, dynamic


def mapped_methods(paths: list[Path], methods: set[str], prefixes: tuple[str, ...]) -> set[str]:
    """The API methods some MCP tool function calls."""
    mapped: set[str] = set()
    for path in paths:
        tree = _parse(path)
        known = _action_catalogs(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _is_tool(node, prefixes):
                called, catalogs, dynamic = _calls(node)
                via_catalog = set().union(*(known.get(c, set()) for c in catalogs)) if dynamic else set()
                mapped |= (called | via_catalog) & methods
    return mapped


def _runtime(root: Path, pattern: str) -> list[Path]:
    out = []
    for path in root.glob(pattern):
        parts = path.relative_to(root).parts
        if path.is_file() and not any(p.startswith(".") or p in SKIP_PARTS for p in parts):
            out.append(path)
    return sorted(out)


def measure(root: Path, prefixes: tuple[str, ...]) -> dict[str, Any] | None:
    """Coverage of the API client by the MCP tools, or None when the repository has no client or no server."""
    clients = _runtime(root, "**/api_client*.py")
    servers = _runtime(root, "**/mcp_server.py")
    if not clients or not servers:
        return None
    registrars = sorted((servers[0].parent / "mcp").glob("*.py"))
    methods = api_methods(clients)
    if not methods:
        return None
    mapped = mapped_methods([servers[0], *registrars], methods, prefixes)
    return {
        "total": len(methods),
        "covered": len(mapped),
        "coverage": len(mapped) / len(methods) * 100,
        "unmapped": sorted(methods - mapped),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-api-parity", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    config = table(project.load(root))
    result = measure(root, config["tool_prefixes"])
    if result is None:
        print("connector-api-parity: OK: no api_client*.py with an mcp_server.py here, nothing to compare")
        return 0
    print(
        f"connector-api-parity: {result['covered']}/{result['total']} API methods reach a tool: "
        f"{result['coverage']:.1f}% (baseline {config['baseline']:.1f}%)"
    )
    failed = result["coverage"] < config["baseline"] - TOLERANCE
    if failed or result["coverage"] < 100:
        label = "FAILED, coverage degraded below the baseline" if failed else "unmapped (tech debt)"
        print(f"connector-api-parity: {label}:")
        for name in result["unmapped"]:
            print(f"  - {name}")
    return 1 if failed else 0
