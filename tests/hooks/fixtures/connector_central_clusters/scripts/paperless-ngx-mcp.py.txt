#!/usr/bin/env python3
"""Verify exact current API-to-MCP action parity."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "paperless_ngx_mcp" / "api"
MCP_ROOT = ROOT / "paperless_ngx_mcp" / "mcp"
EXCLUDED_METHODS = {"close", "request"}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def api_methods() -> set[str]:
    methods: set[str] = set()
    for path in sorted(API_ROOT.glob("api_client_*.py")):
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.ClassDef) or "client" not in node.name.lower():
                continue
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not item.name.startswith("_")
                    and item.name not in EXCLUDED_METHODS
                ):
                    methods.add(item.name)
    return methods


def mcp_methods() -> set[str]:
    methods: set[str] = set()
    for path in sorted(MCP_ROOT.glob("mcp_*.py")):
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if not any(
                    isinstance(target, ast.Name) and target.id == "_ACTIONS"
                    for target in node.targets
                ):
                    continue
                if isinstance(node.value, (ast.Set, ast.Tuple, ast.List)):
                    methods.update(
                        element.value
                        for element in node.value.elts
                        if isinstance(element, ast.Constant)
                        and isinstance(element.value, str)
                    )
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "client"
            ):
                methods.add(node.attr)
    return methods


def main() -> int:
    public = api_methods()
    mapped = mcp_methods().intersection(public)
    missing = sorted(public - mapped)
    extra = sorted(mcp_methods() - public)
    print(f"Paperless-ngx API methods: {len(public)}")
    print(f"Paperless-ngx mapped methods: {len(mapped)}")
    if missing or extra:
        print(f"Missing mappings: {missing}")
        print(f"Unknown mappings: {extra}")
        return 1
    print("Paperless-ngx API-to-MCP action parity: 100%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
