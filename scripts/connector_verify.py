"""Verify one migrated connector over stdio (run with the connector's own python).

Starts the MCP server, checks ``connector://resources`` lists every declared source and that ``ontology://``
and ``shapes://`` resources read. Usage: connector_verify.py <repo-root> [--allow-manifest-alias] (the flag is for dry-runs against the pre-cutover SDK branch). Prints one JSON line; exit 1 on failure.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import tomllib
from pathlib import Path


def server_command(root: Path) -> list[str]:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    name = next((n for n in scripts if n.endswith("-mcp")), next(iter(scripts)))
    return [str(Path(sys.executable).with_name(name)), "--transport", "stdio"]


def declared_source_ids(root: Path) -> list[str]:
    pkgs = [p for p in root.iterdir() if (p / "connector_sources.py").is_file()]
    text = pkgs[0].joinpath("connector_sources.py").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'^        source_id="([^"]+)"', text, re.M)))


async def check(root: Path, allow_alias: bool = False) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cmd = server_command(root)
    out: dict = {"ok": False}
    async with stdio_client(StdioServerParameters(command=cmd[0], args=cmd[1:])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            uris = [str(x.uri) for x in (await s.list_resources()).resources]
            out["resources"] = len(uris)
            body = json.loads((await s.read_resource("connector://resources")).contents[0].text)
            served = sorted(x["source_id"] for x in body["sources"])
            want = declared_source_ids(root)
            out["sources"] = served
            if served != want:
                out["error"] = f"connector://resources lists {served}, declared {want}"
                return out
            if "manifest://connector" in uris and not allow_alias:
                out["error"] = "manifest://connector is still served (hard cutover)"
                return out
            for prefix in ("ontology://", "shapes://"):
                found = [u for u in uris if u.startswith(prefix)]
                if not found:
                    out["error"] = f"no {prefix} resource listed"
                    return out
                for u in found:
                    if not (await s.read_resource(u)).contents:
                        out["error"] = f"{u} read empty"
                        return out
                out[prefix] = len(found)
    out["ok"] = True
    return out


if __name__ == "__main__":
    try:
        result = asyncio.run(check(Path(sys.argv[1]).resolve(), "--allow-manifest-alias" in sys.argv))
    except Exception as exc:  # noqa: BLE001 - the verdict is the failure text
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, sort_keys=True))
    sys.exit(0 if result["ok"] else 1)
