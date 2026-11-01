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

[project.entry-points."scion_sdk.connector"]
demo-mcp = "demo_agent"
"""
MCP_SERVER = """from scion_sdk.config import load_config
from scion_sdk.mcp.server import create_mcp_server
from scion_sdk.mcp.tool_surface import register_tool_surface
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


@pytest.mark.spec("PIPE-GATES-R016.111")
def test_central_pass_is_idempotent_and_bumps_once(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    opts = {"no_lock": True}
    first = cc.migrate_central(root, opts)
    assert first["applied"] and first["rules"] == len(cc.RULE_TABLE)
    assert 'version = "1.0.5"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    second = cc.migrate_central(root, opts)
    assert second["applied"] == []
    assert 'version = "1.0.5"' in (root / "pyproject.toml").read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R016.111")
def test_every_rule_is_ordered_once_and_counted_by_source() -> None:
    order = cc.rule_order()
    assert len(order) == len(set(order)) == len(cc.RULE_TABLE)
    assert sum(cc.rule_counts().values()) == len(cc.RULE_TABLE)


@pytest.mark.spec("PIPE-GATES-R016.111")
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


@pytest.mark.spec("PIPE-GATES-R016.111")
def test_tidy_sorts_imports_and_drops_unused_ones_in_rewritten_files(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    ctx = cc.make_ctx(root, {})
    assert ctx is not None
    (root / "demo_agent/mod.py").write_text("import sys\nimport os\n\nprint(os.name)\n", encoding="utf-8")
    ctx.changed.add("demo_agent/mod.py")
    cc.tidy(ctx)
    assert (root / "demo_agent/mod.py").read_text(encoding="utf-8") == "import os\n\nprint(os.name)\n"


@pytest.mark.spec("PIPE-GATES-R016.111")
def test_a_reviewed_pre_patch_applies_in_the_central_pass(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "batch2", Path(cm.__file__).parents[2] / "scripts/connector_migrate_batch.py"
    )
    assert spec and spec.loader
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "mod.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    patch = tmp_path / "demo.pre.patch"
    patch.write_text("--- a/mod.py\n+++ b/mod.py\n@@ -2 +2 @@\n-b = 2\n+b = 3\n", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    subprocess.run(["git", "init", "-q"], cwd=wt, env=env, check=True)

    class _Led:
        def record(self, *args: object, **kw: object) -> None:
            self.kw = kw

    led = _Led()
    touched = batch.apply_repo_patch(patch, wt, [], led, "demo")  # type: ignore[arg-type]
    assert touched == ["mod.py"] and (wt / "mod.py").read_text(encoding="utf-8") == "a = 1\nb = 3\n"


@pytest.mark.spec("PIPE-GATES-R016.111")
def test_a_pre_patch_that_deletes_a_file_reports_it_as_touched(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "batch3", Path(cm.__file__).parents[2] / "scripts/connector_migrate_batch.py"
    )
    assert spec and spec.loader
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "old.txt").write_text("x\n", encoding="utf-8")
    patch = tmp_path / "demo.central-pre.patch"
    patch.write_text("--- a/old.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    subprocess.run(["git", "init", "-q"], cwd=wt, env=env, check=True)

    class _Led:
        def record(self, *args: object, **kw: object) -> None:
            pass

    assert batch.apply_repo_patch(patch, wt, [], _Led(), "demo") == ["old.txt"]  # type: ignore[arg-type]
    assert not (wt / "old.txt").exists()
