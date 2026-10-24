#!/usr/bin/env python3
"""Verify exact public API-to-condensed-MCP action parity without imports."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


_EXCLUDED_API_METHOD_NAMES = {"authenticate", "close", "request"}


def _is_public_api_method(item: ast.stmt) -> bool:
    """True for a class-body method that is part of the public API surface."""
    return isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (
        item.name.startswith("_") or item.name in _EXCLUDED_API_METHOD_NAMES
    )


def _public_methods_in_class(node: ast.ClassDef) -> set[str]:
    return {item.name for item in node.body if _is_public_api_method(item)}


def _public_api_methods(root: Path) -> set[str]:
    methods: set[str] = set()
    api_dir = root / "firefly_iii_mcp" / "api"
    for path in sorted(api_dir.glob("api_client_*.py")):
        if path.name in {"api_client_base.py", "api_client_firefly_iii.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods |= _public_methods_in_class(node)
    return methods


def _resolve_action_literal_names(node: ast.Call) -> set[str]:
    """String constants passed as the literal action set to resolve_action(...)."""
    if len(node.args) < 2 or not isinstance(
        node.args[1], (ast.Set, ast.List, ast.Tuple)
    ):
        return set()
    return {
        element.value
        for element in node.args[1].elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }


def _client_attribute_action(node: ast.Call) -> str | None:
    """The attribute name of a ``client.<action>(...)`` / ``api.<action>(...)`` call."""
    if (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"client", "api"}
    ):
        return node.func.attr
    return None


def _actions_referenced_by_call(node: ast.Call) -> set[str]:
    actions: set[str] = set()
    if isinstance(node.func, ast.Name) and node.func.id == "resolve_action":
        actions |= _resolve_action_literal_names(node)
    client_action = _client_attribute_action(node)
    if client_action:
        actions.add(client_action)
    return actions


def _condensed_actions(root: Path) -> set[str]:
    actions: set[str] = set()
    mcp_dir = root / "firefly_iii_mcp" / "mcp"
    for path in sorted(mcp_dir.glob("mcp_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                actions |= _actions_referenced_by_call(node)
    return actions


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    methods = _public_api_methods(root)
    actions = _condensed_actions(root)
    missing = sorted(methods - actions)
    unknown = sorted(actions - methods)

    print("Firefly III API-to-MCP parity")
    print(f"API methods: {len(methods)}")
    print(f"Condensed actions: {len(actions)}")
    if missing:
        print("Missing actions: " + ", ".join(missing))
    if unknown:
        print("Unknown actions: " + ", ".join(unknown))
    if missing or unknown or not methods:
        return 1
    print("Coverage: 100.0%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
