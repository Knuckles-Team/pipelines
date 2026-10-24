#!/usr/bin/env python3
"""API-to-MCP integration parity check (local-tool variant).

Fan Manager is a *local* tool: there is no REST/GraphQL backend. Its public
surface is the :class:`fan_manager.api_client.Api` facade, whose methods
re-export the real callables in :mod:`fan_manager.fan_manager`
(``get_temp``, ``get_core_temp``, ``set_fan``, ``auto_set_fan_speed``,
``run_service``).

The MCP tools are *action-routed*: a single tool per domain lives under
``fan_manager/mcp/`` and routes to those module-level callables by importing and
calling them directly (e.g. ``set_fan(fan_level=...)``) rather than through a
networked ``client.method()`` indirection. A REST-shaped verifier that only
looks for ``client.foo``/``api.foo`` attribute access on a single
``mcp_server.py`` would therefore report 0% for a perfectly-integrated local
tool — which is wrong.

This adapted verifier:
  * treats the ``Api`` facade methods as the public API surface, and
  * scans ``mcp_server.py`` **and** every tool module under ``<pkg>/mcp/`` for
    *direct* calls to those callables (``set_fan(...)``) as well as the
    ``client.``/``api.``/``self.`` indirection the golden verifier already
    handles.

It runs in ``--local`` / ``--pre-commit`` mode against the current directory and
exits non-zero only if a real integration gap exists (an ``Api`` method that no
MCP tool wires up).
"""

import ast
import glob
import os
import sys


# Blocking / long-running service entrypoints are NOT request/response MCP tools
# (e.g. ``run_service`` is an infinite ``while True`` daemon loop driven by the
# CLI and the agent service mode). They are excluded from MCP-tool parity for the
# same reason the golden verifier excludes ``authenticate``.
NON_TOOL_METHODS = {"authenticate", "run_service"}


def parse_api_client(filepath):
    """Parse api_client.py for the public Api/Client methods (CONCEPT:FM-OS.governance.service-reads-temperature-through/FAN-002 surface)."""
    with open(filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=filepath)

    methods = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name.lower()
            if "api" in class_name or "client" in class_name:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if (
                            not item.name.startswith("_")
                            and item.name not in NON_TOOL_METHODS
                        ):
                            methods[item.name] = {
                                "line": item.lineno,
                                "class": node.name,
                            }
    return methods


class CallVisitor(ast.NodeVisitor):
    """Collect both direct calls (``foo(...)``) and ``client``/``api``/``self``
    attribute access, so action-routed local tools register as integrated."""

    def __init__(self):
        self.called_names = set()

    def visit_Call(self, node):
        """Record direct/indirect calls wiring the CONCEPT:FM-OS.governance.service-reads-temperature-through/FAN-002 callables."""
        func = node.func
        # Direct call: set_fan(...), get_temp(...)
        if isinstance(func, ast.Name):
            self.called_names.add(func.id)
        # Indirection: client.get_temp(...), api.set_fan(...), self.set_fan(...)
        elif isinstance(func, ast.Attribute):
            self.called_names.add(func.attr)
            if isinstance(func.value, ast.Name) and func.value.id in (
                "client",
                "api",
                "self",
            ):
                self.called_names.add(func.attr)
        # getattr(client, "foo")
        if isinstance(func, ast.Name) and func.id == "getattr":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                if isinstance(node.args[1].value, str):
                    self.called_names.add(node.args[1].value)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        # Bare attribute reference (e.g. passing api.set_fan as a callable)
        if isinstance(node.value, ast.Name) and node.value.id in (
            "client",
            "api",
            "self",
        ):
            self.called_names.add(node.attr)
        self.generic_visit(node)


def collect_called_names(filepaths):
    names = set()
    for filepath in filepaths:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=filepath)
        visitor = CallVisitor()
        visitor.visit(tree)
        names.update(visitor.called_names)
    return names


def verify_agent(agent_dir):
    """Verify every Api method is wired into an MCP tool (CONCEPT:FM-OS.governance.service-reads-temperature-through/FAN-002)."""
    api_clients = glob.glob(
        os.path.join(agent_dir, "**", "api_client.py"), recursive=True
    )
    mcp_servers = glob.glob(
        os.path.join(agent_dir, "**", "mcp_server.py"), recursive=True
    )
    if not api_clients or not mcp_servers:
        return None

    api_client_path = api_clients[0]
    api_methods = parse_api_client(api_client_path)
    if not api_methods:
        return None

    # Scan mcp_server.py plus every tool module under <pkg>/mcp/ — that is where
    # an action-routed local tool actually wires the callables.
    integration_files = list(mcp_servers)
    for tool_file in glob.glob(
        os.path.join(agent_dir, "**", "mcp", "*.py"), recursive=True
    ):
        if os.path.basename(tool_file) != "__init__.py":
            integration_files.append(tool_file)
    integration_files = sorted(set(integration_files))

    called_names = collect_called_names(integration_files)
    mapped = set(api_methods.keys()) & called_names
    unmapped = set(api_methods.keys()) - mapped

    total = len(api_methods)
    coverage = (len(mapped) / total) * 100 if total else 0.0
    return {
        "agent_name": os.path.basename(agent_dir),
        "api_client": api_client_path,
        "integration_files": integration_files,
        "total_methods": total,
        "covered_methods": len(mapped),
        "coverage": coverage,
        "unmapped": sorted(unmapped),
        "mapped": sorted(mapped),
    }


def main():
    """CLI entrypoint for the API-to-MCP parity check (CONCEPT:FM-OS.governance.service-reads-temperature-through/FAN-002)."""
    args = sys.argv[1:]
    # Always operate in local single-package mode for this repo.
    if "--local" in args or "--pre-commit" in args or not args:
        cwd = os.getcwd()
        res = verify_agent(cwd)
        if not res:
            print(
                "Skipping integration parity verification: no "
                "mcp_server.py/api_client.py found in current directory."
            )
            sys.exit(0)

        # Local tool: the Api facade re-exports module-level callables, so every
        # public method should be wired into at least one MCP tool.
        baseline = 100.0
        print(f"=== API-to-MCP Integration Parity Check for: {res['agent_name']} ===")
        print(f"- API client methods : {res['total_methods']}")
        print(f"- Integrated methods : {res['covered_methods']}")
        print(f"- Current Coverage   : {res['coverage']:.1f}%")
        print(f"- Target Baseline    : {baseline:.1f}%")

        if res["coverage"] < (baseline - 0.05):
            print(
                f"\nFAILED: Integration coverage ({res['coverage']:.1f}%) is below "
                f"the required baseline of {baseline:.1f}%."
            )
            print("\nUnmapped API methods (no MCP tool wires these up):")
            for m in res["unmapped"]:
                print(f"  - {m}")
            sys.exit(1)

        print("\nPASSED: every Api method is wired into an MCP tool.")
        sys.exit(0)

    print("Only --local/--pre-commit mode is supported for this package.")
    sys.exit(0)


if __name__ == "__main__":
    main()
