"""connector-standard member: the connector accounts for its whole MCP surface (PIPE-GATES-R014.8).

It runs the ``connector-surface-audit`` checks on the repository root in strict mode
and prints the markdown fix checklist when a part is missing. The reference is
``reference/connector-surface.md``.
"""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.hygiene import connector_surface


def main(argv: list[str]) -> int:
    """1 when the connector at the working directory has a surface gap, else 0."""
    del argv
    record = connector_surface.audit_connector(Path.cwd())
    if record["complete"]:
        return 0
    print(connector_surface.markdown([record]), end="")
    print("connector-surface: see reference/connector-surface.md")
    return 1
