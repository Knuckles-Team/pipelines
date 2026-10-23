"""List the tool names one connector serves over stdio (run with the connector's own python).

Usage: connector_served_tools.py <repo-root>. Prints one `SERVED_TOOLS <JSON list>` line of names (PIPE-GATES-R016.27).
"""

from __future__ import annotations

import asyncio
import json
import sys
import tomllib
from pathlib import Path


def server_command(root: Path) -> list[str]:
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    name = next((n for n in scripts if n.endswith("-mcp")), next(iter(scripts)))
    return [str(Path(sys.executable).with_name(name)), "--transport", "stdio"]


async def served(root: Path) -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cmd = server_command(root)
    async with stdio_client(StdioServerParameters(command=cmd[0], args=cmd[1:])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return sorted(t.name for t in (await s.list_tools()).tools)


if __name__ == "__main__":
    print("SERVED_TOOLS " + json.dumps(asyncio.run(served(Path(sys.argv[1]).resolve()))))
