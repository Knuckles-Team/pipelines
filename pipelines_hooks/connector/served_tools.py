"""The tools a connector's built server actually registers.

Source parsing cannot see the tools the Scion SDK derives from a client class,
so a check that counts tools asks the server instead. This module builds the
connector's server in the connector's own interpreter, lists the tools its
local provider registers, and reads back each name and its input properties.
Pipelines imports no ecosystem package: the probe is a fixed script run in a
child process.

The interpreter is ``$PIPELINES_CONNECTOR_PYTHON``, else ``<root>/.venv``'s
Python, else ``uv run --frozen python`` in the root. A probe that cannot build
the server raises :class:`~pipelines_hooks.core.errors.Unavailable` with the
reason, so CI fails closed and a local run prints ``SKIPPED``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import Unavailable

ENTRY_POINT_GROUP = "scion_sdk.connector"
TIMEOUT_SECONDS = 300
MARKER = "PIPELINES-SERVED-TOOLS:"

PROBE = (
    """
import json, sys
from scion_sdk.connector import build_server
from scion_sdk.mcp.tool_surface import registered_tools
_, mcp = build_server(sys.argv[1], command_args=["--transport", "stdio"])
tools = []
for name, tool in sorted(registered_tools(mcp).items()):
    schema = getattr(tool, "parameters", None) or {}
    tools.append({"name": name, "properties": sorted((schema.get("properties") or {}))})
print("%s" + json.dumps(tools))
"""
    % MARKER
)


@dataclass(frozen=True)
class ServedTool:
    """One registered tool: its name and its input property names."""

    name: str
    properties: tuple[str, ...]


def connector_package(root: Path) -> str | None:
    """The package the one ``scion_sdk.connector`` entry point names, or ``None``."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    points = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("entry-points", {})
    group = points.get(ENTRY_POINT_GROUP, {})
    if len(group) != 1:
        return None
    return str(next(iter(group.values()))).split(":", 1)[0].split(".", 1)[0].strip()


def interpreter(root: Path) -> list[str]:
    explicit = os.environ.get("PIPELINES_CONNECTOR_PYTHON")
    if explicit:
        return [explicit]
    venv = root / ".venv" / "bin" / "python"
    if venv.is_file():
        return [str(venv)]
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--frozen", "--quiet", "python"]
    raise Unavailable("served-tools: no connector interpreter (set PIPELINES_CONNECTOR_PYTHON, or install uv)")


def served_tools(root: Path) -> list[ServedTool] | None:
    """The tools the built server registers; ``None`` when ``root`` declares no connector."""
    package = connector_package(root)
    if package is None:
        return None
    command = [*interpreter(root), "-c", PROBE, package]
    try:
        done = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unavailable(f"served-tools: cannot start the connector interpreter: {exc}") from None
    lines = [line for line in done.stdout.splitlines() if line.startswith(MARKER)]
    if done.returncode or not lines:
        reason = (done.stderr.strip().splitlines() or ["no output"])[-1][:300]
        raise Unavailable(f"served-tools: the server of {package} did not build: {reason}")
    payload = json.loads(lines[-1][len(MARKER) :])
    return [ServedTool(str(item["name"]), tuple(item.get("properties") or ())) for item in payload]


def covers(tool: str, method: str) -> bool:
    """A served tool name covers a client method when it is the method or ends in ``_<method>``."""
    return tool == method or tool.endswith("_" + method)
