"""connector-standard member: the connector accounts for its whole MCP surface (PIPE-GATES-R014.8).

It builds the connector's server, takes the tools it registers (``served_tools``), and runs the
``connector-surface-audit`` checks on the repository root against them in strict mode
and prints the markdown fix checklist when a part is missing. The reference is
``reference/connector-surface.md``.
"""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.connector.served_tools import served_tools
from pipelines_hooks.hygiene import connector_surface


def main(argv: list[str]) -> int:
    """1 when the connector at the working directory has a surface gap, else 0."""
    del argv
    root = Path.cwd()
    served = served_tools(root)
    record = connector_surface.audit_connector(root, served=served)
    if record["complete"]:
        return 0
    print(connector_surface.markdown([record]), end="")
    print("connector-surface: see reference/connector-surface.md")
    return 1
