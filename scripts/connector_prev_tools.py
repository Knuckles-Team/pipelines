"""List the tool names an installed connector serves over stdio (the pre-migration baseline of the post-release check).

Usage: connector_prev_tools.py <python of the venv> <distribution>. Prints one JSON list line; the console script is the
distribution's ``*-mcp`` entry point.
"""

import asyncio
import importlib.metadata as md
import json
import sys
from pathlib import Path


async def names(python: str, dist: str) -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    scripts = [e.name for e in md.distribution(dist).entry_points if e.group == "console_scripts"]
    name = next((n for n in scripts if n.endswith("-mcp")), scripts[0])
    cmd = str(Path(python).with_name(name))
    async with stdio_client(StdioServerParameters(command=cmd, args=["--transport", "stdio"])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return sorted(t.name for t in (await s.list_tools()).tools)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(names(sys.argv[1], sys.argv[2]))))
