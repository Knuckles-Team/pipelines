"""connector-ontology-map migrate --central: the orchestrated pass and the batch driver flags (PIPE-GATES-R016.100)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.hygiene import connector_central as cc
from pipelines_hooks.hygiene import connector_migrate as cm

PYPROJECT = """[project]
name = "demo-agent"
version = "1.0.4"
dependencies = [ "agent-connector-sdk[mcp]>=0.4.3,<1.0.0",]

[project.scripts]
demo-mcp = "demo_agent.mcp_server:mcp_server"

[project.entry-points."agent_connector_sdk.connector"]
demo-mcp = "demo_agent"
"""
MCP_SERVER = """from agent_connector_sdk.config import load_config
from agent_connector_sdk.mcp.server import create_mcp_server
from agent_connector_sdk.mcp.tool_surface import register_tool_surface
import sys

from demo_agent.api_client import Api
from demo_agent.auth import get_client

__version__ = "1.0.4"


def get_mcp_instance():
    load_config()
    args, mcp, middlewares = create_mcp_server(name="demo", version=__version__, instructions="Demo.")
    register_tool_surface(mcp, client_cls=Api, get_client=get_client, service="demo", tools_module=sys.modules[__name__])
    for mw in middlewares:
        mcp.add_middleware(mw)
    return mcp, args, middlewares


def mcp_server() -> None:
    mcp, args, middlewares = get_mcp_instance()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    elif args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        sys.exit(1)


if __name__ == "__main__":
    mcp_server()
"""


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "demo-agent"
    pkg = root / "demo_agent"
    pkg.mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## [1.0.4] - 2026-01-01\n", encoding="utf-8")
    (pkg / "__init__.py").write_text('__version__ = "1.0.4"\n', encoding="utf-8")
    (pkg / "mcp_server.py").write_text(MCP_SERVER, encoding="utf-8")
    (pkg / "__main__.py").write_text(
        "from demo_agent.mcp_server import mcp_server\n\nif __name__ == '__main__':\n    mcp_server()\n",
        encoding="utf-8",
    )
    (pkg / "api_client.py").write_text("class Api:\n    pass\n", encoding="utf-8")
    (pkg / "auth.py").write_text("def get_client():\n    return None\n", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "--", "."]):
        subprocess.run(["git", *cmd], cwd=root, env=env, check=True, capture_output=True)
    return root


@pytest.mark.spec("PIPE-GATES-R016.100")
def test_central_pass_is_idempotent_and_bumps_once(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    opts = {"no_lock": True}
    first = cc.migrate_central(root, opts)
    assert first["applied"] and first["rules"] == len(cc.RULE_TABLE)
    assert 'version = "1.0.5"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    second = cc.migrate_central(root, opts)
    assert second["applied"] == []
    assert 'version = "1.0.5"' in (root / "pyproject.toml").read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R016.100")
def test_every_rule_is_ordered_once_and_counted_by_source() -> None:
    order = cc.rule_order()
    assert len(order) == len(set(order)) == len(cc.RULE_TABLE)
    assert sum(cc.rule_counts().values()) == len(cc.RULE_TABLE)


@pytest.mark.spec("PIPE-GATES-R016.100")
def test_central_driver_flags(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    out = tmp_path / "report.json"
    code = cm.main(["--central", "--root", str(root), "--no-lock", "--out", str(out)])
    assert code in (0, 2) and "review" in json.loads(out.read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location(
        "batch", Path(cm.__file__).parents[2] / "scripts/connector_migrate_batch.py"
    )
    assert spec and spec.loader
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    assert batch.CENTRAL_MESSAGE and callable(batch.central_verify)
