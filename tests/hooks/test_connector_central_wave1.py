"""Wave 1 central migration rules (PIPE-GATES-R016.50-.67): bootstrap, version, ingest declaration, entry points."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

from pipelines_hooks.hygiene.connector_central import base, wave1
from pipelines_hooks.hygiene.connector_central.wave1 import ORDER, ORDER_LAST

PYPROJECT = """[project]
name = "demo-mcp"
version = "1.2.3"
dependencies = [ "agent-connector-sdk[mcp,graphql]>=0.4.3,<1.0.0", "requests>=2.0",]

[project.scripts]
demo-mcp = "demo_mcp.mcp_server:mcp_server"

[project.optional-dependencies]
mcp = [ "agent-connector-sdk[mcp]>=0.4.3,<1.0.0",]
all = [ "agent-connector-sdk[mcp]>=0.4.3,<1.0.0",]
test = [ "pytest>=9",]

# CONCEPT: skill federation
[project.entry-points."agent_connector_sdk.skill_providers"]
demo-mcp = "demo_mcp.skills"

[project.entry-points."agent_connector_sdk.ontology_providers"]
demo-mcp = "demo_mcp.ontology"

# The one declared connector identity.
[project.entry-points."agent_connector_sdk.connector"]
demo-mcp = "demo_mcp"

[tool.setuptools.package-data]
demo_mcp = [ "ontology/**", "skills/**",]
"""

MCP_SERVER = '''#!/usr/bin/python
import logging
import sys
from typing import Any

from agent_connector_sdk.config import load_config, setting
from agent_connector_sdk.mcp.server import create_mcp_server
from agent_connector_sdk.mcp.tool_surface import register_tool_surface
from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger
from starlette.requests import Request
from starlette.responses import JSONResponse

from demo_mcp.api_client import Api
from demo_mcp.auth import get_client

__version__ = "0.1.37"

logger = get_logger(name="demo-mcp")
logger.setLevel(logging.INFO)

FLAG = setting("DEMO_FLAG", "x")


def helper(x: Any) -> Any:
    logger.debug("helper")
    return x


def register_things_tools(mcp: FastMCP):
    @mcp.tool(tags={"things"})
    async def things(client=get_client) -> dict:
        return {}


def get_mcp_instance() -> tuple[Any, ...]:
    """Initialize and return the MCP instance."""
    load_config()
    args, mcp, middlewares = create_mcp_server(
        name="demo MCP",
        version=__version__,
        instructions="Demo server.",
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse({"status": "OK"})

    register_tool_surface(
        mcp,
        client_cls=Api,
        get_client=get_client,
        service="demo-mcp",
        tools_module=sys.modules[__name__],
%s    )

    for mw in middlewares:
        mcp.add_middleware(mw)
    return mcp, args, middlewares


def mcp_server() -> None:
    mcp, args, middlewares = get_mcp_instance()
    print(f"demo-mcp MCP v{__version__}", file=sys.stderr)
    print("\\nStarting MCP Server", file=sys.stderr)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    elif args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        logger.error("Invalid transport", extra={"transport": args.transport})
        sys.exit(1)


if __name__ == "__main__":
    mcp_server()
'''

GITLAB_SHAPE = MCP_SERVER % "" + ""
SOURCES = '''"""Data sources."""

# ruff: noqa: E501
from __future__ import annotations

from agent_connector_sdk.ingest.live_declaration import source_meta
from agent_connector_sdk.ingest.sources import IngestSourceDeclaration, IngestSourceSpec

CONNECTOR = "demo-mcp"

SOURCES = (source_meta(tool="demo_list", source_id="things", record_type="Thing", id_field="id"),)

SCHEMA_MAPPINGS = {
    "Thing": {
        "fields": {"a": "xsd:string", "b": "xsd:integer"},
        "ontology_class": "Concept",
    },
    "Other": {
        "fields": {"a": "xsd:string", "b": "xsd:integer"},
        "ontology_class": "Agent",
    },
    "Solo": {
        "fields": {"z": "xsd:string"},
        "ontology_class": "Agent",
    },
}

RESOURCES = ()


def declaration() -> IngestSourceDeclaration:
    """The declaration the server assembles from this module."""
    specs = []
    for item in SOURCES:
        for entry in item["connector_sources"]:
            body = {k: v for k, v in entry.items() if k not in ("tool", "mapping")}
            specs.append(
                IngestSourceSpec.model_validate({**body, "tools": (entry["tool"],)})
            )
    return IngestSourceDeclaration.model_validate(
        {
            "connector": CONNECTOR,
            "sources": specs,
            "schema_mappings": SCHEMA_MAPPINGS,
            "resources": RESOURCES,
        }
    )
'''
BUMP = """[bumpversion]
current_version = 1.2.3
commit = True
tag = True

[bumpversion:file:pyproject.toml]
search = version = "{current_version}"
replace = version = "{new_version}"

[bumpversion:file:README.md]
search = Version: {current_version}
replace = Version: {new_version}

[bumpversion:file(docker-img):docker/Dockerfile]
search = =={current_version}"
replace = =={new_version}"
"""
SCAFFOLD_INIT = '''"""Demo."""

import importlib
import inspect

__all__: list[str] = []

CORE_MODULES: list[str] = ["demo_mcp.api_client"]
OPTIONAL_MODULES = {"demo_mcp.mcp_server": "mcp"}


def _expose_members(module):
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj):
            globals()[name] = obj


for module_name in CORE_MODULES:
    _expose_members(importlib.import_module(module_name))


def _import_module_safely(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


def __getattr__(name):
    raise AttributeError(name)
'''


def _make(
    tmp_path: Path, *, surface: str = "", init: str = '__version__ = "0.1.0"\n', server: str | None = None
) -> Path:
    root = tmp_path / "demo-mcp"
    pkg = root / "demo_mcp"
    (pkg / "skills").mkdir(parents=True)
    (pkg / "ontology").mkdir()
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (pkg / "__init__.py").write_text(init, encoding="utf-8")
    (pkg / "__main__.py").write_text(
        'from demo_mcp.mcp_server import mcp_server\n\nif __name__ == "__main__":\n    mcp_server()\n', encoding="utf-8"
    )
    (pkg / "mcp_server.py").write_text(server if server is not None else MCP_SERVER % surface, encoding="utf-8")
    (pkg / "api_client.py").write_text("class Api:\n    pass\n", encoding="utf-8")
    (pkg / "auth.py").write_text("def get_client():\n    return None\n", encoding="utf-8")
    (pkg / "connector_sources.py").write_text(SOURCES, encoding="utf-8")
    (pkg / "skills" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "skills" / "one.md").write_text("x\n", encoding="utf-8")
    (root / ".bumpversion.cfg").write_text(BUMP, encoding="utf-8")
    (root / "README.md").write_text("# Demo\n\nPackage version: 1.2.3.\n\nText.\n", encoding="utf-8")
    (root / "tests" / "test_ingest_sources.py").write_text(
        "from demo_mcp.connector_sources import declaration as declared\n\n\ndef test_x():\n    assert declared().connector == 'demo-mcp'\n",
        encoding="utf-8",
    )
    return root


def _ctx(root: Path, **options: object) -> base.Ctx:
    ctx = base.make_ctx(root, dict(options))
    assert ctx is not None
    return ctx


def _run(ctx: base.Ctx, ids: tuple[str, ...]) -> None:
    for rid in ids:
        base.RULES[rid](ctx)


def _snapshot(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*")) if p.is_file()
    }


def _text(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _notes(ctx: base.Ctx, rid: str) -> list[dict]:
    return [i for i in ctx.review.items if i["step"] == rid]


# --- registration -----------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.50")
def test_order_lists_every_wave1_rule_and_all_are_registered() -> None:
    assert ORDER == tuple("w1." + s for s in "g3 g4 g5 g6 g1 g2 k1 k2 k3 k4 i1 i2 l1 l2 l3 l4 g7".split())
    assert ORDER_LAST == ("w1.h",)
    assert set(ORDER) | set(ORDER_LAST) == {r for r in base.RULES if r.startswith("w1.")}


# --- g.1 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.50")
def test_g1_entry_point_names_the_connector_value(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.g1"))
    assert tomllib.loads(_text(root, "pyproject.toml"))["project"]["entry-points"]["agent_connector_sdk.connector"] == {
        "demo-mcp": "demo_mcp:connector"
    }


@pytest.mark.spec("PIPE-GATES-R016.50")
def test_g1_unmatched_value_goes_to_review_and_unreviewed_bootstrap_is_untouched(tmp_path: Path) -> None:
    root = _make(tmp_path)
    text = _text(root, "pyproject.toml").replace('demo-mcp = "demo_mcp"\n', 'demo-mcp = "demo_mcp.other"\n')
    (root / "pyproject.toml").write_text(text, encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.g1"))
    assert _notes(ctx, "w1.g1")[0]["blocking"] and 'demo-mcp = "demo_mcp.other"' in _text(root, "pyproject.toml")
    root2 = _make(tmp_path / "b", server="def get_mcp_instance():\n    x = 1\n")
    ctx2 = _ctx(root2)
    _run(ctx2, ("w1.g3", "w1.g4", "w1.g1"))
    assert 'demo-mcp = "demo_mcp"\n' in _text(root2, "pyproject.toml")  # connector not declared: entry point untouched


# --- g.2 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.51")
def test_g2_console_script_becomes_serve(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.g2"))
    assert tomllib.loads(_text(root, "pyproject.toml"))["project"]["scripts"] == {
        "demo-mcp": "agent_connector_sdk.cli:serve"
    }


@pytest.mark.spec("PIPE-GATES-R016.51")
def test_g2_unknown_script_value_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    text = _text(root, "pyproject.toml").replace("demo_mcp.mcp_server:mcp_server", "demo_mcp.cli:main")
    (root / "pyproject.toml").write_text(text, encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.g2"))
    assert _notes(ctx, "w1.g2")[0]["blocking"] and "demo_mcp.cli:main" in _text(root, "pyproject.toml")


# --- g.3 / g.6 ------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.52")
def test_g3_bootstrap_is_deleted_and_only_its_imports_are_pruned(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3",))
    text = _text(root, "demo_mcp/mcp_server.py")
    tree = ast.parse(text)
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert names == {"helper", "register_things_tools"}
    for gone in (
        "create_mcp_server",
        "register_tool_surface",
        "load_config",
        "JSONResponse",
        "__version__",
        "import sys",
    ):
        assert gone not in text
    for kept in ("setting", "get_client", "get_logger", "logging", "FastMCP"):
        assert kept in text
    assert "from demo_mcp.api_client import Api" not in text and "__main__" not in text
    assert not ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_g3_registration_beyond_the_plain_surface_goes_to_review_untouched(tmp_path: Path) -> None:
    server = MCP_SERVER % ""
    server = server.replace(
        "    for mw in middlewares:", "    register_kg_ingest_tools(mcp)\n\n    for mw in middlewares:"
    )
    root = _make(tmp_path, server=server)
    before = _snapshot(root)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.g5", "w1.g6", "w1.g1", "w1.g2"))
    assert _notes(ctx, "w1.g3")[0]["blocking"]
    assert "register_kg_ingest_tools" in _notes(ctx, "w1.g3")[0]["detail"]
    assert _snapshot(root) == before


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_g3_os_environ_lines_registered_tags_and_prompts_go_to_review(tmp_path: Path) -> None:
    server = MCP_SERVER % ""
    server = server.replace("    load_config()\n", "    load_config()\n    os.environ['TERM'] = 'dumb'\n")
    root = _make(tmp_path, server=server)
    before = _snapshot(root)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3",))
    assert "os.environ" in _notes(ctx, "w1.g3")[0]["detail"] and _snapshot(root) == before


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_g3_copies_surface_keywords_and_a_module_constant_instructions(tmp_path: Path) -> None:
    server = (
        MCP_SERVER
        % '        tool_prefix="dm",\n        verbose_targets=[{"client_cls": Api, "get_client": get_client}],\n        action_dispatch=True,\n'
    )
    server = server.replace('instructions="Demo server.",', "instructions=INSTRUCTIONS,")
    server = server.replace("FLAG = setting", 'INSTRUCTIONS = "Const instructions."\nFLAG = setting')
    root = _make(tmp_path, server=server)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4"))
    init = _text(root, "demo_mcp/__init__.py")
    assert "from demo_mcp.mcp_server import INSTRUCTIONS" in init and "instructions=INSTRUCTIONS" in init
    assert 'tool_prefix="dm"' in init and "action_dispatch=True" in init
    assert "verbose_targets=({'client_cls': Api, 'get_client': get_client},)" in init


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_g3_manifest_keyword_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path, surface="        manifest=OPERATIONS,\n")
    before = _snapshot(root)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3",))
    assert "manifest" in _notes(ctx, "w1.g3")[0]["detail"] and _snapshot(root) == before


@pytest.mark.spec("PIPE-GATES-R016.55")
def test_g6_health_route_is_deleted_with_the_bootstrap(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g6"))
    assert "/health" not in _text(root, "demo_mcp/mcp_server.py") and "w1.g6" in ctx.applied and not ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.55")
def test_g6_stray_health_route_elsewhere_is_reported(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "demo_mcp" / "extra.py").write_text(
        '@mcp.custom_route("/health", methods=["GET"])\nasync def h(r): ...\n', encoding="utf-8"
    )
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g6"))
    assert _notes(ctx, "w1.g6") and not _notes(ctx, "w1.g6")[0]["blocking"]


# --- g.4 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.53")
def test_g4_init_declares_the_connector(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4"))
    init = _text(root, "demo_mcp/__init__.py")
    assert "from agent_connector_sdk.connector import Connector" in init
    assert "from demo_mcp.api_client import Api" in init and "from demo_mcp.auth import get_client" in init
    assert 'tools="demo_mcp.mcp_server"' in init and 'instructions="Demo server."' in init
    ast.parse(init)


@pytest.mark.spec("PIPE-GATES-R016.53")
def test_g4_without_an_extractable_bootstrap_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path, server="x = 1\n")
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4"))
    assert _notes(ctx, "w1.g4")[0]["blocking"] and "connector =" not in _text(root, "demo_mcp/__init__.py")


# --- g.5 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.54")
def test_g5_main_calls_run(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.g5"))
    assert (
        _text(root, "demo_mcp/__main__.py")
        == 'from agent_connector_sdk import run\n\nif __name__ == "__main__":\n    run()\n'
    )


@pytest.mark.spec("PIPE-GATES-R016.54")
def test_g5_other_main_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "demo_mcp" / "__main__.py").write_text("import sys\nprint('x')\n", encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.g5"))
    assert _notes(ctx, "w1.g5")[0]["blocking"] and _text(root, "demo_mcp/__main__.py") == "import sys\nprint('x')\n"


# --- g.7 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.56")
def test_g7_test_importing_deleted_function_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "tests" / "test_custom.py").write_text(
        "from demo_mcp.mcp_server import get_mcp_instance\n", encoding="utf-8"
    )
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g7"))
    note = _notes(ctx, "w1.g7")[0]
    assert note["path"] == "tests/test_custom.py" and "build_server" in note["detail"] and note["blocking"]


@pytest.mark.spec("PIPE-GATES-R016.56")
def test_g7_scaffold_test_is_left_to_rule_h(tmp_path: Path) -> None:
    root = _make(tmp_path)
    body = "from demo_mcp.mcp_server import get_mcp_instance\n"
    (root / "tests" / "test_startup.py").write_text(body, encoding="utf-8")
    ctx = _ctx(root)
    fp = wave1.fingerprint(ctx, body)
    ctx.options["fingerprints"] = {"test_startup.py": [fp]}
    _run(ctx, ("w1.g3", "w1.g7"))
    assert not _notes(ctx, "w1.g7")


# --- k.1 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.58")
def test_k1_version_assignments_are_deleted(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.k1"))
    assert "__version__" not in _text(root, "demo_mcp/__init__.py")
    ast.parse(_text(root, "demo_mcp/__init__.py"))


@pytest.mark.spec("PIPE-GATES-R016.58")
def test_k1_version_still_read_in_the_module_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "demo_mcp" / "api_client.py").write_text(
        '__version__ = "1.0.0"\n\n\ndef v():\n    return __version__\n', encoding="utf-8"
    )
    ctx = _ctx(root)
    _run(ctx, ("w1.k1",))
    assert _notes(ctx, "w1.k1")[0]["blocking"] and "__version__" in _text(root, "demo_mcp/api_client.py")


@pytest.mark.spec("PIPE-GATES-R016.58")
def test_k1_connector_importer_gets_metadata_version(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "demo_mcp" / "version.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    (root / "demo_mcp" / "banner.py").write_text(
        "from demo_mcp.version import __version__\n\nprint(__version__)\n", encoding="utf-8"
    )
    ctx = _ctx(root)
    _run(ctx, ("w1.k1",))
    assert not (root / "demo_mcp" / "version.py").exists()
    assert "from importlib.metadata import version as _v" in _text(root, "demo_mcp/banner.py")
    assert '__version__ = _v("demo-mcp")' in _text(root, "demo_mcp/banner.py")


@pytest.mark.spec("PIPE-GATES-R016.58")
def test_k1_test_importer_with_other_use_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "tests" / "test_v.py").write_text(
        "from demo_mcp import __version__\n\n\ndef test_v():\n    print(__version__)\n", encoding="utf-8"
    )
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.k1"))
    assert _notes(ctx, "w1.k1") and '__version__ = "0.1.0"' in _text(root, "demo_mcp/__init__.py")


# --- k.2 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.59")
def test_k2_bumpversion_reduced_to_pyproject_only(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.k2",))
    assert _text(root, ".bumpversion.cfg") == (
        "[bumpversion]\ncurrent_version = 1.2.3\ncommit = True\ntag = True\n\n[bumpversion:file:pyproject.toml]\n"
        'search = version = "{current_version}"\nreplace = version = "{new_version}"\n'
    )


@pytest.mark.spec("PIPE-GATES-R016.59")
def test_k2_without_pyproject_section_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / ".bumpversion.cfg").write_text("[bumpversion]\ncurrent_version = 1.0.0\n", encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.k2",))
    assert _notes(ctx, "w1.k2") and _text(root, ".bumpversion.cfg") == "[bumpversion]\ncurrent_version = 1.0.0\n"


# --- k.3 / k.4 ----------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.60")
def test_k3_readme_package_version_line_is_deleted(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "README.md").write_text(
        "# Demo\n\nPackage version: 1.2.3.\n\n| a | Version 1.2.3; ok |\n\nVersion 2 of the thing.\n", encoding="utf-8"
    )
    ctx = _ctx(root)
    _run(ctx, ("w1.k3",))
    assert _text(root, "README.md") == "# Demo\n\n\n| a | ok |\n\nVersion 2 of the thing.\n"


@pytest.mark.spec("PIPE-GATES-R016.60")
def test_k3_prose_mentions_are_left(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "README.md").write_text("The package version: 1.2.3 is current.\n", encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.k3",))
    assert not ctx.changed


@pytest.mark.spec("PIPE-GATES-R016.61")
def test_k4_version_assertions_are_deleted(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "tests" / "test_v.py").write_text(
        "import demo_mcp\nfrom demo_mcp import __version__\n\n\ndef test_only():\n    assert __version__ == '0.1.0'\n\n\n"
        "def test_more():\n    assert demo_mcp.__version__ == '0.1.0'\n    assert 1 == 1\n",
        encoding="utf-8",
    )
    ctx = _ctx(root)
    _run(ctx, ("w1.k4",))
    out = _text(root, "tests/test_v.py")
    assert "test_only" not in out and "__version__" not in out and "assert 1 == 1" in out
    assert "from demo_mcp import __version__" not in out


@pytest.mark.spec("PIPE-GATES-R016.61")
def test_k4_other_comparisons_are_left(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "tests" / "test_v.py").write_text("def test_a(v):\n    assert v.version == '1'\n", encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.k4",))
    assert not ctx.changed


# --- i.1 / i.2 ----------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.62")
def test_i1_declaration_is_deleted_and_call_sites_use_load_declaration(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.i1",))
    src = _text(root, "demo_mcp/connector_sources.py")
    assert "def declaration" not in src and "CONNECTOR" not in src and "IngestSource" not in src
    test = _text(root, "tests/test_ingest_sources.py")
    assert "from agent_connector_sdk.ingest import load_declaration" in test
    assert 'load_declaration("demo_mcp").connector' in test and "declared" not in test
    ast.parse(src)
    ast.parse(test)


@pytest.mark.spec("PIPE-GATES-R016.62")
def test_i1_module_attribute_and_connector_constant_users_are_rewritten(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "tests" / "test_mod.py").write_text(
        "from demo_mcp import connector_sources as cs\n\n\ndef test_a():\n    assert cs.declaration().connector == cs.CONNECTOR\n",
        encoding="utf-8",
    )
    ctx = _ctx(root)
    _run(ctx, ("w1.i1",))
    out = _text(root, "tests/test_mod.py")
    assert 'load_declaration("demo_mcp").connector == connector_name("demo_mcp")' in out
    assert "connector_sources" not in out and "agent_connector_sdk.connector_identity import connector_name" in out


@pytest.mark.spec("PIPE-GATES-R016.62")
def test_i1_modified_declaration_body_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    p = root / "demo_mcp" / "connector_sources.py"
    p.write_text(
        p.read_text(encoding="utf-8").replace("specs = []", "specs = []  # noqa\n    specs.append(1)"), encoding="utf-8"
    )
    before = _snapshot(root)
    ctx = _ctx(root)
    _run(ctx, ("w1.i1",))
    assert _notes(ctx, "w1.i1")[0]["blocking"] and _snapshot(root) == before


@pytest.mark.spec("PIPE-GATES-R016.62")
def test_i1_callable_passed_around_is_reviewed_untouched(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "tests" / "test_ingest_sources.py").write_text(
        "from demo_mcp.connector_sources import declaration\n\nF = declaration\n", encoding="utf-8"
    )
    before = _snapshot(root)
    ctx = _ctx(root)
    _run(ctx, ("w1.i1",))
    assert _notes(ctx, "w1.i1")[0]["blocking"] and _snapshot(root) == before


@pytest.mark.spec("PIPE-GATES-R016.63")
def test_i2_identical_field_dicts_become_field_sets(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.i2",))
    src = _text(root, "demo_mcp/connector_sources.py")
    ns: dict = {}
    exec(
        compile(
            src.split("def declaration")[0]
            .replace("from agent_connector_sdk.ingest.live_declaration import source_meta", "source_meta = dict")
            .replace("from agent_connector_sdk.ingest.sources import IngestSourceDeclaration, IngestSourceSpec", ""),
            "x",
            "exec",
        ),
        ns,
    )
    assert ns["SCHEMA_VERSION"] == 2 and ns["FIELD_SETS"] == {"fields_1": {"a": "xsd:string", "b": "xsd:integer"}}
    assert ns["SCHEMA_MAPPINGS"]["Thing"] == {"field_sets": ["fields_1"], "ontology_class": "Concept"}
    assert ns["SCHEMA_MAPPINGS"]["Solo"] == {"fields": {"z": "xsd:string"}, "ontology_class": "Agent"}


@pytest.mark.spec("PIPE-GATES-R016.63")
def test_i2_without_repeated_dicts_or_literals_nothing_changes(tmp_path: Path) -> None:
    root = _make(tmp_path)
    p = root / "demo_mcp" / "connector_sources.py"
    text = p.read_text(encoding="utf-8").replace('"b": "xsd:integer"', '"c": "xsd:integer"', 1)
    p.write_text(text, encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.i2",))
    assert not ctx.changed
    p.write_text(text.replace("SCHEMA_MAPPINGS = {", "SCHEMA_MAPPINGS = dict(**{"), encoding="utf-8")
    p.write_text(text.replace('"ontology_class": "Concept"', '"ontology_class": cls()'), encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.i2",))
    assert _notes(ctx, "w1.i2") and not ctx.changed


# --- l.1 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.64")
def test_l1_conventional_provider_tables_and_their_comment_are_deleted(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.l1",))
    out = _text(root, "pyproject.toml")
    assert "skill_providers" not in out and "ontology_providers" not in out and "CONCEPT" not in out
    assert "The one declared connector identity" in out
    tomllib.loads(out)


@pytest.mark.spec("PIPE-GATES-R016.64")
def test_l1_non_conventional_value_stays_and_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    text = _text(root, "pyproject.toml").replace('"demo_mcp.skills"', '"demo_mcp.myskills"')
    (root / "pyproject.toml").write_text(text, encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.l1",))
    out = _text(root, "pyproject.toml")
    assert "skill_providers" in out and "ontology_providers" not in out
    assert _notes(ctx, "w1.l1")[0]["blocking"]


# --- l.2 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.65")
def test_l2_empty_marker_deleted_when_package_data_covers_the_content(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.l2",))
    assert not (root / "demo_mcp/skills/__init__.py").exists() and (root / "demo_mcp/skills/one.md").exists()


@pytest.mark.spec("PIPE-GATES-R016.65")
def test_l2_missing_package_data_glob_is_added(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "demo_mcp" / "prompts").mkdir()
    (root / "demo_mcp" / "prompts" / "__init__.py").write_text("# marker\n", encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.l2",))
    data = tomllib.loads(_text(root, "pyproject.toml"))["tool"]["setuptools"]["package-data"]["demo_mcp"]
    assert "prompts/*.json" in data and "skills/**" in data
    assert not (root / "demo_mcp/prompts/__init__.py").exists()


@pytest.mark.spec("PIPE-GATES-R016.65")
def test_l2_non_empty_marker_is_kept(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "demo_mcp" / "skills" / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.l2",))
    assert (root / "demo_mcp/skills/__init__.py").exists()


# --- l.3 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.66")
def test_l3_scaffold_is_deleted_with_the_connector_and_test_imports_follow(tmp_path: Path) -> None:
    root = _make(tmp_path, init=SCAFFOLD_INIT)
    (root / "tests" / "test_api.py").write_text("from demo_mcp import Api\n", encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.l3"))
    init = _text(root, "demo_mcp/__init__.py")
    assert "CORE_MODULES" not in init and "connector = Connector(" in init and init.startswith('"""Demo."""')
    assert _text(root, "tests/test_api.py") == "from demo_mcp.api_client import Api\n"
    assert not ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.66")
def test_l3_unresolvable_name_keeps_the_scaffold_and_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path, init=SCAFFOLD_INIT)
    (root / "tests" / "test_api.py").write_text("from demo_mcp import Mystery\n", encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.l3"))
    assert _notes(ctx, "w1.g4")[0]["blocking"] and "CORE_MODULES" in _text(root, "demo_mcp/__init__.py")
    assert _text(root, "tests/test_api.py") == "from demo_mcp import Mystery\n"


@pytest.mark.spec("PIPE-GATES-R016.66")
def test_l3_scaffold_with_extra_code_is_not_deleted(tmp_path: Path) -> None:
    root = _make(tmp_path, init=SCAFFOLD_INIT + "\nEXTRA = compute()\n")
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.l3"))
    assert "CORE_MODULES" in _text(root, "demo_mcp/__init__.py")
    assert _notes(ctx, "w1.l3")


@pytest.mark.spec("PIPE-GATES-R016.66")
def test_l3_scaffold_survives_when_the_bootstrap_was_not_migrated(tmp_path: Path) -> None:
    server = (MCP_SERVER % "").replace(
        "    register_tool_surface(", "    other_registration(mcp)\n    register_tool_surface("
    )
    root = _make(tmp_path, init=SCAFFOLD_INIT, server=server)
    ctx = _ctx(root)
    _run(ctx, ("w1.g3", "w1.g4", "w1.l3"))
    assert "CORE_MODULES" in _text(root, "demo_mcp/__init__.py")


# --- l.4 ------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.67")
def test_l4_sdk_floor_merged_extras_and_dropped_one_element_extras(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ctx = _ctx(root)
    _run(ctx, ("w1.l4",))
    data = tomllib.loads(_text(root, "pyproject.toml"))["project"]
    assert data["dependencies"] == ["agent-connector-sdk[graphql,mcp]>=0.5.2,<0.6.0", "requests>=2.0"]
    assert data["optional-dependencies"] == {"test": ["pytest>=9"]}
    assert ctx.pkg_name and base.SDK_PIN.startswith("agent-connector-sdk[mcp]>=0.5.2")


@pytest.mark.spec("PIPE-GATES-R016.67")
def test_l4_pin_uses_base_sdk_pin_for_the_plain_mcp_extra(tmp_path: Path) -> None:
    root = _make(tmp_path)
    text = _text(root, "pyproject.toml").replace("[mcp,graphql]>=0.4.3,<1.0.0", "[mcp]>=0.4.3,<1.0.0")
    (root / "pyproject.toml").write_text(text, encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.l4",))
    assert f'"{base.SDK_PIN}"' in _text(root, "pyproject.toml")


@pytest.mark.spec("PIPE-GATES-R016.67")
def test_l4_multi_element_extra_stays_and_missing_dependency_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    text = _text(root, "pyproject.toml").replace(
        'all = [ "agent-connector-sdk[mcp]>=0.4.3,<1.0.0",]', 'all = [ "agent-connector-sdk[mcp]>=0.4.3,<1.0.0", "x",]'
    )
    (root / "pyproject.toml").write_text(text, encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.l4",))
    assert "all" in tomllib.loads(_text(root, "pyproject.toml"))["project"]["optional-dependencies"]
    root2 = _make(tmp_path / "b")
    (root2 / "pyproject.toml").write_text(
        _text(root2, "pyproject.toml").replace("agent-connector-sdk", "agent-sdk-other"), encoding="utf-8"
    )
    ctx2 = _ctx(root2)
    _run(ctx2, ("w1.l4",))
    assert _notes(ctx2, "w1.l4")[0]["blocking"]


# --- h ------------------------------------------------------------------------------------------------------
def test_normalisation_replaces_names_and_semvers_and_drops_comments() -> None:
    a = wave1.normalise(
        ("demo-mcp", "demo-mcp", "demo_mcp"), '# c\n\nX = "demo_mcp 1.2.3"  \nSPEC = "CONN-DEMO-MCP-R001"\n'
    )
    b = wave1.normalise(
        ("kafka-mcp", "kafka-mcp", "kafka_mcp"), 'X = "kafka_mcp 9.0.1"\n# other\nSPEC = "CONN-KAFKA-MCP-R001"\n'
    )
    assert a == b and wave1.digest(a) == wave1.digest(b)


@pytest.mark.spec("PIPE-GATES-R016.57")
def test_h_scaffold_test_matching_a_fingerprint_is_deleted(tmp_path: Path) -> None:
    root = _make(tmp_path)
    body = '"""CONN-DEMO-MCP-R001"""\nPACKAGE = "demo_mcp"\n'
    (root / "tests" / "test_default_content_surfaces.py").write_text(body, encoding="utf-8")
    ctx = _ctx(root)
    ctx.options["fingerprints"] = {"test_default_content_surfaces.py": [wave1.fingerprint(ctx, body)]}
    _run(ctx, ("w1.h",))
    assert not (root / "tests/test_default_content_surfaces.py").exists()
    assert "tests/test_default_content_surfaces.py" in ctx.deleted


@pytest.mark.spec("PIPE-GATES-R016.57")
def test_h_unmatched_file_is_left_and_reported_with_its_hash(tmp_path: Path) -> None:
    root = _make(tmp_path)
    body = "def test_custom():\n    assert True\n"
    (root / "tests" / "test_startup.py").write_text(body, encoding="utf-8")
    ctx = _ctx(root, fingerprints={"test_startup.py": ["0000000000000000"]})
    _run(ctx, ("w1.h",))
    note = next(i for i in ctx.review.items if i["path"] == "tests/test_startup.py")
    assert not note["blocking"] and wave1.fingerprint(ctx, body) in note["detail"]
    assert (root / "tests/test_startup.py").exists()


@pytest.mark.spec("PIPE-GATES-R016.57")
def test_h_ontology_parent_link_with_pending_entries_is_reviewed(tmp_path: Path) -> None:
    root = _make(tmp_path)
    ok = "PENDING_NEW_PARENT = frozenset()\n"
    bad = 'PENDING_NEW_PARENT = frozenset({"X"})\n'
    f = root / "tests" / "test_ontology_parent_link.py"
    f.write_text(bad, encoding="utf-8")
    ctx = _ctx(root)
    ctx.options["fingerprints"] = {
        "test_ontology_parent_link.py": [wave1.fingerprint(ctx, bad), wave1.fingerprint(ctx, ok)]
    }
    _run(ctx, ("w1.h",))
    assert f.exists() and "PENDING_NEW_PARENT" in ctx.review.items[0]["detail"]
    f.write_text(ok, encoding="utf-8")
    ctx2 = _ctx(root, fingerprints=ctx.options["fingerprints"])
    _run(ctx2, ("w1.h",))
    assert not f.exists()


@pytest.mark.spec("PIPE-GATES-R016.57")
def test_h_conftest_env_line_only_file_is_deleted_and_fixture_conftest_keeps_its_fixtures(tmp_path: Path) -> None:
    root = _make(tmp_path)
    conf = root / "tests" / "conftest.py"
    conf.write_text('import os\n\n# env\nos.environ["KNOWLEDGE_GRAPH_SYNC_BACKGROUND"] = "False"\n', encoding="utf-8")
    ctx = _ctx(root)
    _run(ctx, ("w1.h",))
    assert not conf.exists()
    conf.write_text(
        'import os\n\nimport pytest\n\nos.environ["KNOWLEDGE_GRAPH_SYNC_BACKGROUND"] = "False"\n\n\n@pytest.fixture\ndef f():\n    return 1\n',
        encoding="utf-8",
    )
    ctx2 = _ctx(root)
    _run(ctx2, ("w1.h",))
    out = conf.read_text(encoding="utf-8")
    assert "KNOWLEDGE_GRAPH_SYNC_BACKGROUND" not in out and "def f()" in out and "import os" not in out


# --- whole-pass behaviour -------------------------------------------------------------------------------------
def test_full_pass_is_idempotent_and_leaves_valid_python(tmp_path: Path) -> None:
    root = _make(tmp_path)
    (root / "tests" / "conftest.py").write_text(
        'import os\nos.environ["KNOWLEDGE_GRAPH_SYNC_BACKGROUND"] = "False"\n', encoding="utf-8"
    )
    ctx = _ctx(root)
    _run(ctx, ORDER + ORDER_LAST)
    assert not [i for i in ctx.review.items if i["blocking"]], ctx.review.items
    after = _snapshot(root)
    for rel, text in after.items():
        if rel.endswith(".py"):
            ast.parse(text)
    tomllib.loads(after["pyproject.toml"])
    ctx2 = _ctx(root)
    _run(ctx2, ORDER + ORDER_LAST)
    assert _snapshot(root) == after and not ctx2.changed and not ctx2.deleted


def test_unmigrated_shape_is_left_whole_and_a_second_run_is_stable(tmp_path: Path) -> None:
    server = (MCP_SERVER % "").replace("    load_config()\n", "    load_config()\n    os.environ['X'] = '1'\n")
    root = _make(tmp_path, server=server)
    ctx = _ctx(root)
    _run(ctx, ORDER + ORDER_LAST)
    first = _snapshot(root)
    assert _notes(ctx, "w1.g3")[0]["blocking"]
    assert (
        "get_mcp_instance" in first["demo_mcp/mcp_server.py"] and 'demo-mcp = "demo_mcp"\n' in first["pyproject.toml"]
    )
    ctx2 = _ctx(root)
    _run(ctx2, ORDER + ORDER_LAST)
    assert _snapshot(root) == first
