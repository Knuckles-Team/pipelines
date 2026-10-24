"""g.3/g.4/g.5 shapes found across the fleet, one fixture per refusal cluster (PIPE-GATES-R016.52-.54).

Each fixture is built from the real shape of a fleet repo (named in the test). The contract is unchanged: an exact
shape is migrated, anything else is refused untouched with a reason; where the SDK cannot express a value, the reason
names the missing SDK capability.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pipelines_hooks.hygiene.connector_central import base, wave1  # noqa: F401  (registers the rules)

PYPROJECT = """[project]
name = "demo-mcp"
version = "1.2.3"

[project.scripts]
demo-mcp = "demo_mcp.mcp_server:mcp_server"

[project.entry-points."agent_connector_sdk.connector"]
demo-mcp = "demo_mcp"
"""

HEAD = """import sys
from typing import Any

from agent_connector_sdk.config import load_config
from agent_connector_sdk.mcp.server import create_mcp_server
from agent_connector_sdk.mcp.tool_surface import register_tool_surface
from fastmcp.utilities.logging import get_logger
from starlette.requests import Request
from starlette.responses import JSONResponse

from demo_mcp.api_client import Api
from demo_mcp.auth import get_client
%s
__version__ = "0.1.37"
logger = get_logger(name="demo-mcp")
"""

HEALTH = """
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse({"status": "OK"})
"""

CLIENT = "        client_cls=Api,\n        get_client=get_client,\n"
OWN = "        tools_module=sys.modules[__name__],\n"

STANDARD = """    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    elif args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
"""


def _server(
    *,
    top: str = "",
    before: str = HEALTH,
    surface: str = CLIENT + OWN,
    after: str = "",
    tags: str = "",
    ret: str = "mcp, args, middlewares",
    dispatch: str = STANDARD,
    banner: str = '    print(f"demo-mcp MCP v{__version__}", file=sys.stderr)\n',
    unpack: str = "mcp, args, middlewares",
    body: str = "",
) -> str:
    return (
        HEAD % ""
        + top
        + f"""

def register_things_tools(mcp):
    return None


def get_mcp_instance() -> tuple[Any, ...]:
    load_config()
    args, mcp, middlewares = create_mcp_server(
        name="demo MCP",
        version=__version__,
        instructions="Demo server.",
    )
{before}{body}
    {tags}register_tool_surface(
        mcp,
        service="demo-mcp",
{surface}    )
{after}
    for mw in middlewares:
        mcp.add_middleware(mw)
    return {ret}


def mcp_server() -> None:
    {unpack} = get_mcp_instance()
{banner}{dispatch}

if __name__ == "__main__":
    mcp_server()
"""
    )


def _repo(tmp_path: Path, server: str, files: dict[str, str] | None = None) -> base.Ctx:
    root = tmp_path / "demo-mcp"
    pkg = root / "demo_mcp"
    pkg.mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "api_client.py").write_text("class Api:\n    pass\n", encoding="utf-8")
    (pkg / "auth.py").write_text("def get_client():\n    return None\n", encoding="utf-8")
    (pkg / "mcp_server.py").write_text(server, encoding="utf-8")
    for rel, text in (files or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    ctx = base.make_ctx(root, {})
    assert ctx is not None
    return ctx


def _migrate(ctx: base.Ctx) -> str:
    for rid in ("w1.g3", "w1.g4"):
        base.RULES[rid](ctx)
    return (ctx.pkg / "__init__.py").read_text(encoding="utf-8")


def _blocking(ctx: base.Ctx, rid: str = "w1.g3") -> list[str]:
    return [i["detail"] for i in ctx.review.items if i["step"] == rid and i["blocking"]]


def _refused_untouched(ctx: base.Ctx, before: str) -> str:
    (detail,) = _blocking(ctx)
    assert (ctx.pkg / "mcp_server.py").read_text(encoding="utf-8") == before
    return detail


# --- (1) transport dispatch variants ---------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.52")
def test_dispatch_with_a_stdio_fallback_else_is_the_sdk_run_loop(tmp_path: Path) -> None:
    """adguard-home-agent, jena-mcp, lakekeeper-mcp, lucerna-mcp, spark-mcp: stdio is the else branch."""
    dispatch = STANDARD.replace(
        '    if args.transport == "stdio":\n        mcp.run(transport="stdio")\n    elif', "    if"
    )
    ctx = _repo(tmp_path, _server(dispatch=dispatch))
    init = _migrate(ctx)
    assert "transports=" not in init and "get_mcp_instance" not in (ctx.pkg / "mcp_server.py").read_text()
    assert not _blocking(ctx)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_dispatch_with_extra_stderr_banner_lines_and_an_error_exit(tmp_path: Path) -> None:
    """freshrss-agent: the SDK run() prints the same banner lines; the invalid-transport else exits non-zero."""
    banner = (
        '    print(f"FreshRSS MCP v{__version__}", file=sys.stderr)\n'
        '    print("\\nStarting MCP Server", file=sys.stderr)\n'
        '    print(f"  Transport: {args.transport.upper()}", file=sys.stderr)\n'
    )
    dispatch = STANDARD[: STANDARD.rindex("    else:")] + (
        '    else:\n        logger.error(f"Invalid transport: {args.transport}")\n        sys.exit(1)\n'
    )
    ctx = _repo(tmp_path, _server(banner=banner, dispatch=dispatch))
    _migrate(ctx)
    assert not _blocking(ctx)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_dispatch_serving_a_subset_declares_the_transports(tmp_path: Path) -> None:
    """okta-agent: stdio and streamable-http only; the SDK would otherwise also offer sse."""
    dispatch = (
        '    if args.transport == "streamable-http":\n'
        '        mcp.run(transport="streamable-http", host=args.host, port=args.port)\n'
        "    else:\n"
        '        mcp.run(transport="stdio")\n'
    )
    ctx = _repo(tmp_path, _server(dispatch=dispatch, unpack="mcp, args, _middlewares, *_"))
    init = _migrate(ctx)
    assert 'transports=("stdio", "streamable-http",),' in init
    assert any("served only stdio, streamable-http" in i["detail"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_dispatch_that_changes_what_a_transport_does_is_refused(tmp_path: Path) -> None:
    dispatch = STANDARD.replace('mcp.run(transport="sse", host=args.host, port=args.port)', 'mcp.run(transport="sse")')
    server = _server(dispatch=dispatch)
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "standard transport dispatch" in _refused_untouched(ctx, server)


# --- (2) tools_module from the package ----------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.52")
def test_tools_module_imported_from_the_package_becomes_a_dotted_tools_value(tmp_path: Path) -> None:
    """aris-mcp, archimate-mcp, paperless-ngx-mcp: `from <pkg>.mcp import mcp_aris`."""
    server = _server(
        top="from demo_mcp.mcp import mcp_aris\n",
        surface=CLIENT + "        tools_module=mcp_aris,\n",
        tags="registered_tags = ",
        after="    _ = registered_tags\n",
    )
    ctx = _repo(tmp_path, server, {"demo_mcp/mcp/__init__.py": "", "demo_mcp/mcp/mcp_aris.py": ""})
    init = _migrate(ctx)
    assert 'tools="demo_mcp.mcp.mcp_aris"' in init and "mcp_aris" not in (ctx.pkg / "mcp_server.py").read_text()


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_tools_module_that_is_not_a_package_module_is_refused(tmp_path: Path) -> None:
    server = _server(top="import os\n", surface=CLIENT + "        tools_module=os,\n")
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "tools_module" in _refused_untouched(ctx, server)


# --- (3) client omitted --------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.52")
def test_surface_without_client_declares_no_api(tmp_path: Path) -> None:
    """arr-mcp, atlassian-agent, camunda-mcp: only verbose_targets (+ own tools)."""
    surface = (
        OWN + '        verbose_targets=[{"client_cls": Api, "get_client": lambda: get_client().v7, "prefix": "v7"}],\n'
    )
    ctx = _repo(tmp_path, _server(surface=surface))
    init = _migrate(ctx)
    assert "api=" not in init and "get_client=" not in init.replace("'get_client'", "")
    assert 'tools="demo_mcp.mcp_server"' in init and "lambda: get_client().v7" in init
    assert not _blocking(ctx)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_computed_client_class_stays_in_review(tmp_path: Path) -> None:
    """uptime-kuma-agent: `client_cls=_optional_client_type()`."""
    server = _server(surface="        client_cls=make(),\n        get_client=get_client,\n" + OWN)
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "client_cls as a plain name" in _refused_untouched(ctx, server)


# --- (4) registrars / tool_registry / manifest -----------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.52")
def test_registrars_become_discovery_of_the_module_namespace(tmp_path: Path) -> None:
    """technitium-dns-mcp, twenty-mcp: `registrars=[register_x_tools, ...]` imported into mcp_server.py."""
    top = "from demo_mcp.mcp.zones import register_zones_tools\nfrom demo_mcp.mcp.users import register_user_tools\n"
    server = _server(top=top, surface=CLIENT + "        registrars=[register_zones_tools, register_user_tools],\n")
    server = server.replace("def register_things_tools(mcp):\n    return None\n\n\n", "")
    ctx = _repo(tmp_path, server)
    init = _migrate(ctx)
    text = (ctx.pkg / "mcp_server.py").read_text()
    assert 'tools="demo_mcp.mcp_server"' in init
    assert "register_zones_tools" in text and "register_user_tools" in text  # kept: discovery finds them there
    assert any("sorted register_<tag>_tools order" in i["detail"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_registrars_with_another_register_function_in_the_module_are_refused(tmp_path: Path) -> None:
    top = "from demo_mcp.mcp.zones import register_zones_tools\n"
    server = _server(top=top, surface=CLIENT + "        registrars=[register_zones_tools],\n")
    ctx = _repo(tmp_path, server)  # register_things_tools is also defined here
    _migrate(ctx)
    assert "register_things_tools" in _refused_untouched(ctx, server)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_literal_tool_registry_with_derived_tags_is_expressed_as_discovery(tmp_path: Path) -> None:
    """erpnext-agent: `("resource", "RESOURCETOOL", register_resource_tools)` is what discovery derives."""
    top = '\nTOOL_REGISTRY = [("things", "THINGSTOOL", register_things_tools)]\n'
    server = _server(top=top, surface=CLIENT + "        tool_registry=TOOL_REGISTRY,\n")
    ctx = _repo(tmp_path, server)
    init = _migrate(ctx)
    assert 'tools="demo_mcp.mcp_server"' in init and "tool_registry" not in init
    assert "TOOL_REGISTRY" in (ctx.pkg / "mcp_server.py").read_text()


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_imported_tool_registry_with_derived_tags_names_that_module(tmp_path: Path) -> None:
    """gramps-mcp / onetrust-api shape: `from <pkg>.mcp import TOOL_REGISTRY` with the registrars bound there."""
    registry = 'from demo_mcp.mcp.a import register_a_tools\n\nTOOL_REGISTRY = [("a", "ATOOL", register_a_tools)]\n'
    top = "from demo_mcp.mcp import TOOL_REGISTRY\n"
    server = _server(top=top, surface=CLIENT + "        tool_registry=TOOL_REGISTRY,\n")
    ctx = _repo(tmp_path, server, {"demo_mcp/mcp/__init__.py": registry, "demo_mcp/mcp/a.py": ""})
    init = _migrate(ctx)
    assert 'tools="demo_mcp.mcp"' in init


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_manifest_becomes_the_first_verbose_target(tmp_path: Path) -> None:
    """mattermost-mcp, vaultwarden-mcp: the SDK takes manifest only inside a verbose target of the same prefix."""
    top = '\nOPERATION_MANIFEST = [{"method": "x", "name": "y"}]\n'
    server = _server(top=top, surface=CLIENT + OWN + "        manifest=OPERATION_MANIFEST,\n")
    ctx = _repo(tmp_path, server)
    init = _migrate(ctx)
    assert "api=" not in init
    assert "verbose_targets=({'client_cls': Api, 'get_client': get_client, 'manifest': OPERATION_MANIFEST},)," in init
    assert "from demo_mcp.mcp_server import OPERATION_MANIFEST" in init


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_manifest_keeps_the_given_verbose_targets_after_the_main_client(tmp_path: Path) -> None:
    top = "\nM = []\n"
    extra = '        verbose_targets=[{"client_cls": Api, "get_client": get_client, "prefix": "p"}],\n'
    ctx = _repo(tmp_path, _server(top=top, surface=CLIENT + OWN + "        manifest=M,\n" + extra))
    init = _migrate(ctx)
    ast.parse(init)
    assert init.index("'manifest': M") < init.index("'prefix': 'p'")


# --- (5) log lines that read only the registered tags -----------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.52")
@pytest.mark.parametrize(
    "line",
    [
        '    logger.info("Registered condensed tool tags", extra={"tags": registered_tags})\n',
        '    logger.info("Registered condensed tool surfaces: count=%d", len(registered_tags))\n',
        '    logger.debug("Registered condensed tool tags: %s", registered_tags)\n',
    ],
)
def test_logging_of_the_registered_tags_goes_with_the_bootstrap(tmp_path: Path, line: str) -> None:
    """keycloak-agent, langfuse-agent, legal-peripherals-mcp, lgtm-mcp, kafka-mcp, atlassian-agent."""
    ctx = _repo(tmp_path, _server(tags="registered_tags = ", after=line))
    _migrate(ctx)
    assert not _blocking(ctx) and "registered_tags" not in (ctx.pkg / "mcp_server.py").read_text()


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_logging_that_reads_anything_else_stays_in_review(tmp_path: Path) -> None:
    server = _server(tags="registered_tags = ", after='    logger.info("tags %s %s", registered_tags, args)\n')
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "logger.info" in _refused_untouched(ctx, server)


# --- (6) dead locals and the inert --openapi-file import -------------------------------------------------------------------
LISTMONK_BODY = """    imported_tools = []
    imported_resources = []
    if getattr(args, "openapi_file", None):
        try:
            imported_tools, imported_resources = load(args.openapi_file)
            for tool in imported_tools:
                mcp.add_tool(tool)
        except Exception:
            sys.exit(1)
"""
LISTMONK_AFTER = """    register_things_tools(mcp)
    for tool in imported_tools:
        mcp.add_tool(tool)
    for resource in imported_resources:
        mcp.add_resource(resource)
"""


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_inert_openapi_import_block_and_its_dead_lists_are_deleted(tmp_path: Path) -> None:
    """listmonk-api, servicenow-api: the SDK parser defines no --openapi-file flag, so the block never runs."""
    server = _server(body=LISTMONK_BODY, after=LISTMONK_AFTER, ret="mcp, args, middlewares, imported_tools")
    ctx = _repo(tmp_path, server)
    init = _migrate(ctx)
    assert not _blocking(ctx) and "imported_tools" not in (ctx.pkg / "mcp_server.py").read_text()
    assert "extra_registrations=(register_things_tools,)," in init
    assert any("never ran" in i["detail"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_openapi_block_under_a_different_condition_stays_in_review(tmp_path: Path) -> None:
    body = LISTMONK_BODY.replace('getattr(args, "openapi_file", None)', "args.openapi_file")
    server = _server(body=body, after=LISTMONK_AFTER)
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert _blocking(ctx)


# --- (7) /health routes -------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.52")
def test_constant_health_payload_with_headers_is_deleted(tmp_path: Path) -> None:
    """arr-mcp: `JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})`."""
    before = HEALTH.replace('{"status": "OK"}', '{"status": "ok"}, headers={"Cache-Control": "no-store"}')
    ctx = _repo(tmp_path, _server(before=before))
    _migrate(ctx)
    assert not _blocking(ctx) and "custom_route" not in (ctx.pkg / "mcp_server.py").read_text()


# --- (8) mcp_server() without get_mcp_instance ----------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.52")
def test_hand_built_server_names_the_registration_context_adapter_to_write(tmp_path: Path) -> None:
    """bellwether-mcp, world-reference-mcp: `mcp, args, _m, clients = build_server()`."""
    server = "def mcp_server():\n    mcp, args, _m, clients = build_server()\n    mcp.run(transport='stdio')\n"
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "register_tools(context: RegistrationContext)" in _refused_untouched(ctx, server)


# --- other shapes ----------------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.52")
def test_comment_mentioning_get_mcp_instance_in_another_module_does_not_block(tmp_path: Path) -> None:
    """arr-mcp, gramps-mcp, onetrust-api: `# consumed by mcp_server.get_mcp_instance().` in `mcp/__init__.py`."""
    other = '"""``mcp_server.get_mcp_instance`` discovers these."""\n# consumed by mcp_server.get_mcp_instance().\n'
    ctx = _repo(tmp_path, _server(), {"demo_mcp/mcp/__init__.py": other})
    _migrate(ctx)
    assert not _blocking(ctx)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_code_using_get_mcp_instance_in_another_module_still_blocks(tmp_path: Path) -> None:
    other = "from demo_mcp.mcp_server import get_mcp_instance\n"
    server = _server()
    ctx = _repo(tmp_path, server, {"demo_mcp/other.py": other})
    _migrate(ctx)
    assert "another module uses get_mcp_instance" in _refused_untouched(ctx, server)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_imported_function_called_with_the_server_gets_a_registration_context_adapter(tmp_path: Path) -> None:
    """SDK 0.5.3 hands every extra registration a RegistrationContext, so an imported `f(mcp)` needs an adapter."""
    server = _server(top="from demo_mcp.kg import register_kg_tools\n", after="    register_kg_tools(mcp)\n")
    ctx = _repo(tmp_path, server, {"demo_mcp/kg.py": "def register_kg_tools(mcp):\n    return None\n"})
    init = _migrate(ctx)
    assert "from demo_mcp.kg import register_kg_tools" in init and "extra_registrations=(_register_kg_tools,)," in init
    assert (
        "def _register_kg_tools(context: RegistrationContext) -> None:\n    register_kg_tools(context.server)" in init
    )
    assert "from agent_connector_sdk.connector_hooks import RegistrationContext" in init
    ast.parse(init)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_server_and_args_must_come_first_in_the_returned_tuple(tmp_path: Path) -> None:
    server = _server(ret="args, mcp, middlewares")
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "does not return the server and its arguments first" in _refused_untouched(ctx, server)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_omitted_tools_module_is_not_defaulted_to_mcp_server(tmp_path: Path) -> None:
    """adguard-home-agent: no tools_module; the Connector must not name `mcp_server` as the tools module."""
    ctx = _repo(tmp_path, _server(surface=CLIENT))
    init = _migrate(ctx)
    assert "tools=" not in init and "api=Api" in init


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_omitted_tools_module_with_a_package_tools_module_is_refused(tmp_path: Path) -> None:
    """The SDK loads `<pkg>.tools` by default, which the old surface did not."""
    server = _server(surface=CLIENT)
    ctx = _repo(tmp_path, server, {"demo_mcp/tools.py": ""})
    _migrate(ctx)
    assert "demo_mcp.tools exists" in _refused_untouched(ctx, server)


# --- g.5 ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.54")
def test_g5_main_with_a_docstring_and_future_import_is_the_plain_entry(tmp_path: Path) -> None:
    """bellwether-mcp, home-assistant-agent, world-reference-mcp: docstring, `from __future__`, shebang."""
    main = (
        '#!/usr/bin/python\n"""Run the server."""\n\nfrom __future__ import annotations\n\n'
        'from demo_mcp.mcp_server import mcp_server\n\nif __name__ == "__main__":\n    mcp_server()\n'
    )
    ctx = _repo(tmp_path, _server(), {"demo_mcp/__main__.py": main})
    for rid in ("w1.g3", "w1.g4", "w1.g5"):
        base.RULES[rid](ctx)
    assert (ctx.pkg / "__main__.py").read_text() == wave1._MAIN
    assert not [i for i in ctx.review.items if i["blocking"]]


# --- g.4: tests that exercise the lazy-import scaffold ---------------------------------------------------------------------------------
SCAFFOLD_INIT = '''"""Demo."""
import importlib

CORE_MODULES = ["demo_mcp.api_client"]
OPTIONAL_MODULES = {"demo_mcp.mcp_server": "mcp"}


def _expose_members(module):
    return None


def _import_module_safely(module_name):
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


for _module_name in CORE_MODULES:
    _module = _import_module_safely(_module_name)


def __getattr__(name):
    raise AttributeError(name)


__all__: list[str] = []
'''


@pytest.mark.spec("PIPE-GATES-R016.53")
def test_g4_deletes_the_tests_that_import_the_scaffold_helpers(tmp_path: Path) -> None:
    """home-assistant-agent, servicenow-api: `test_init_coverage` imports `_import_module_safely`."""
    test = (
        "import pytest\nfrom unittest.mock import patch\n\n\n"
        "def test_init_coverage():\n    from demo_mcp import _import_module_safely\n\n"
        "    assert _import_module_safely('os') is not None\n\n\n"
        "def test_other():\n    assert 1 == 1\n"
    )
    ctx = _repo(tmp_path, _server(), {"tests/test_cov.py": test})
    (ctx.pkg / "__init__.py").write_text(SCAFFOLD_INIT, encoding="utf-8")
    _migrate(ctx)
    new = (ctx.root / "tests/test_cov.py").read_text()
    assert "test_init_coverage" not in new and "def test_other" in new
    assert "_import_module_safely" not in (ctx.pkg / "__init__.py").read_text()
    assert not _blocking(ctx, "w1.g4")
    assert any("exercise the removed lazy-import scaffold" in i["detail"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.53")
def test_g4_keeps_the_scaffold_when_a_read_sits_outside_a_test(tmp_path: Path) -> None:
    """A module-level `dir(<pkg>)` is not a scaffold-only test: the scaffold is kept, the file untouched."""
    test = (
        "import demo_mcp\n\nNAMES = dir(demo_mcp)\n\n\n"
        "def test_init_coverage():\n    from demo_mcp import _import_module_safely\n\n"
        "    assert _import_module_safely('os') is not None\n"
    )
    ctx = _repo(tmp_path, _server(), {"tests/test_cov.py": test})
    (ctx.pkg / "__init__.py").write_text(SCAFFOLD_INIT, encoding="utf-8")
    before = (ctx.root / "tests/test_cov.py").read_text()
    _migrate(ctx)
    (detail,) = _blocking(ctx, "w1.g4")
    assert "dir(demo_mcp)" in detail and (ctx.root / "tests/test_cov.py").read_text() == before


@pytest.mark.spec("PIPE-GATES-R016.53")
def test_g4_deletes_tests_that_read_the_package_through_the_scaffold(tmp_path: Path) -> None:
    """audio-transcriber, stirlingpdf-agent: `dir(<pkg>)`, `hasattr(<pkg>, ...)`, `<pkg>._MCP_AVAILABLE` tests."""
    test = (
        "import pytest\nimport demo_mcp\n\n\n"
        "def test_flags():\n    assert isinstance(demo_mcp._MCP_AVAILABLE, bool)\n\n\n"
        "def test_exposed():\n    assert hasattr(demo_mcp, 'Api')\n\n\n"
        "def test_dir():\n    assert 'Api' in dir(demo_mcp)\n\n\n"
        "def test_dunder():\n    assert hasattr(demo_mcp, '__version__')\n\n\n"
        "def test_missing():\n    with pytest.raises(AttributeError):\n        _ = demo_mcp.nope\n"
    )
    ctx = _repo(tmp_path, _server(), {"tests/test_cov.py": test})
    (ctx.pkg / "__init__.py").write_text(SCAFFOLD_INIT, encoding="utf-8")
    _migrate(ctx)
    new = (ctx.root / "tests/test_cov.py").read_text()
    assert "test_flags" not in new and "test_exposed" not in new and "def test_dir" not in new
    assert "def test_dunder" in new and "def test_missing" in new
    assert not _blocking(ctx, "w1.g4")
    assert "CORE_MODULES" not in (ctx.pkg / "__init__.py").read_text()


@pytest.mark.spec("PIPE-GATES-R016.53")
def test_g4_deletes_a_test_file_whose_every_test_is_scaffold_only(tmp_path: Path) -> None:
    """audio-transcriber, home-assistant-agent: the whole coverage file only tests the lazy-import scaffold."""
    test = (
        "import demo_mcp\nfrom unittest.mock import patch\n\n\n"
        "def test_exposed():\n    assert hasattr(demo_mcp, 'Api')\n\n\n"
        "def test_import_error():\n    from demo_mcp import _import_module_safely\n\n"
        "    with patch('importlib.import_module', side_effect=ImportError):\n"
        "        assert _import_module_safely('x') is None\n"
    )
    ctx = _repo(tmp_path, _server(), {"tests/test_init_cov.py": test})
    (ctx.pkg / "__init__.py").write_text(SCAFFOLD_INIT, encoding="utf-8")
    _migrate(ctx)
    assert not (ctx.root / "tests/test_init_cov.py").exists()
    assert not _blocking(ctx, "w1.g4")
    assert any("test_exposed" in i["detail"] for i in ctx.review.items if i["step"] == "w1.g4")


@pytest.mark.spec("PIPE-GATES-R016.53")
def test_g4_keeps_a_scaffold_only_file_that_another_file_imports(tmp_path: Path) -> None:
    test = "import demo_mcp\n\n\ndef test_exposed():\n    assert hasattr(demo_mcp, 'Api')\n"
    other = "from tests.test_init_cov import helper\n"
    ctx = _repo(tmp_path, _server(), {"tests/test_init_cov.py": test, "tests/test_other.py": other})
    (ctx.pkg / "__init__.py").write_text(SCAFFOLD_INIT, encoding="utf-8")
    _migrate(ctx)
    (detail,) = _blocking(ctx, "w1.g4")
    assert "tests/test_other.py imports the file" in detail
    assert (ctx.root / "tests/test_init_cov.py").read_text() == test


@pytest.mark.spec("PIPE-GATES-R016.53")
def test_g4_does_not_repeat_the_g3_reason_when_there_is_nothing_to_extract(tmp_path: Path) -> None:
    """ansible-tower-mcp, wger-agent: `mcp_server.py` only re-exports the bootstrap that lives in `mcp/mcp_server.py`."""
    wrapper = "from demo_mcp.mcp.mcp_server import (\n    get_mcp_instance,\n    mcp_server,\n)\n"
    ctx = _repo(tmp_path, wrapper)
    for rid in ("w1.g3", "w1.g4"):
        base.RULES[rid](ctx)
    (g3,) = _blocking(ctx, "w1.g3")
    assert "re-exports get_mcp_instance from demo_mcp.mcp.mcp_server" in g3
    assert not _blocking(ctx, "w1.g4")


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_g3_accepts_forwarded_command_args_and_delegates_the_build_server_wrapper(tmp_path: Path) -> None:
    """craft-suite-api, immich-api, vector-mcp: `command_args=command_args` is the SDK's own argv handling."""
    server = _server().replace("def get_mcp_instance() ->", "def get_mcp_instance(*, command_args=None) ->")
    server = server.replace(
        'instructions="Demo server.",', 'instructions="Demo server.",\n        command_args=command_args,'
    )
    ok = _repo(tmp_path / "a", server)
    base.RULES["w1.g3"](ok)
    assert not _blocking(ok)
    wrapper = server.replace(
        "def mcp_server() -> None:",
        "def build_server(*, command_args=None):\n    return get_mcp_instance(command_args=command_args)[0]\n\n\n"
        "def mcp_server() -> None:",
    )
    ctx = _repo(tmp_path / "b", wrapper)
    base.RULES["w1.g3"](ctx)
    assert not _blocking(ctx)
    text = (ctx.pkg / "mcp_server.py").read_text()
    assert 'return _sdk_build_server("demo_mcp", command_args=command_args)[1]' in text
    assert "from agent_connector_sdk.connector import build_server as _sdk_build_server" in text
    assert "get_mcp_instance" not in text
    ast.parse(text)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_g3_refuses_a_wrapper_that_does_more_than_return_the_server(tmp_path: Path) -> None:
    server = _server().replace("def get_mcp_instance() ->", "def get_mcp_instance(*, command_args=None) ->")
    server = server.replace(
        'instructions="Demo server.",', 'instructions="Demo server.",\n        command_args=command_args,'
    )
    wrapper = server.replace(
        "def mcp_server() -> None:",
        "def build_server(*, command_args=None):\n    return get_mcp_instance(command_args=command_args)\n\n\n"
        "def mcp_server() -> None:",
    )
    ctx = _repo(tmp_path, wrapper)
    before = (ctx.pkg / "mcp_server.py").read_text()
    base.RULES["w1.g3"](ctx)
    (detail,) = _blocking(ctx)
    assert "still uses get_mcp_instance outside the bootstrap" in detail
    assert (ctx.pkg / "mcp_server.py").read_text() == before


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_options_dispatch_is_the_sdk_run_loop(tmp_path: Path) -> None:
    """craft-suite-api, immich-api: `options = {} if stdio else {host, port}` then `mcp.run(transport=..., **options)`."""
    dispatch = (
        '    options = {} if args.transport == "stdio" else {"host": args.host, "port": args.port}\n'
        "    mcp.run(transport=args.transport, **options)\n"
    )
    ctx = _repo(tmp_path, _server(dispatch=dispatch))
    init = _migrate(ctx)
    assert not _blocking(ctx) and "transports=" not in init
    other = dispatch.replace('"stdio"', '"sse"')
    ctx2 = _repo(tmp_path / "x", _server(dispatch=other))
    _migrate(ctx2)
    assert any("banner/dispatch shape" in d or "dispatch" in d for d in _blocking(ctx2))


EGERIA_ISOLATION = """    saved_argv = sys.argv
    if command_args is not None:
        sys.argv = [saved_argv[0] if saved_argv else "demo-mcp", *command_args]
    try:
        args, mcp, middlewares = create_mcp_server(
            name="demo MCP",
            version=__version__,
            instructions=instructions,
        )
    finally:
        sys.argv = saved_argv
"""


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_instructions_variable_and_argv_isolation_are_the_sdk_defaults(tmp_path: Path) -> None:
    """egeria-mcp: `instructions = (...)` then the sys.argv save/restore around create_mcp_server."""
    server = _server().replace("def get_mcp_instance() ->", "def get_mcp_instance(command_args=None) ->")
    server = server.replace(
        "    load_config()\n    args, mcp, middlewares = create_mcp_server(\n"
        '        name="demo MCP",\n        version=__version__,\n        instructions="Demo server.",\n    )\n',
        '    load_config()\n    instructions = ("Demo "\n    "server.")\n' + EGERIA_ISOLATION,
    )
    assert "saved_argv" in server
    ctx = _repo(tmp_path, server)
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert 'instructions="Demo server.",' in init
    assert "saved_argv" not in (ctx.pkg / "mcp_server.py").read_text()


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_bootstrap_in_a_second_module_is_extracted_and_the_wrapper_loses_the_reexport(tmp_path: Path) -> None:
    """ansible-tower-mcp, wger-agent: mcp_server.py re-exports the bootstrap of `<pkg>.mcp.mcp_server`."""
    wrapper = (
        '"""Wrapper."""\n\nfrom demo_mcp.mcp.mcp_server import (\n    get_mcp_instance,\n    mcp_server,\n'
        "    register_things_tools,\n)\n\n"
        '__all__ = [\n    "get_mcp_instance",\n    "mcp_server",\n    "register_things_tools",\n]\n'
    )
    real = _server(top="__all__ = []\n").replace("from demo_mcp.api_client", "from demo_mcp.api_client")
    reexport = 'from demo_mcp.mcp.mcp_server import get_mcp_instance, mcp_server\n\n__all__ = ["get_mcp_instance", "mcp_server"]\n'
    ctx = _repo(tmp_path, wrapper, {"demo_mcp/mcp/__init__.py": reexport, "demo_mcp/mcp/mcp_server.py": real})
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert "connector = Connector(" in init and 'tools="demo_mcp.mcp.mcp_server"' in init
    new_wrapper = (ctx.pkg / "mcp_server.py").read_text()
    assert "get_mcp_instance" not in new_wrapper and "mcp_server," not in new_wrapper
    assert "register_things_tools" in new_wrapper
    assert "get_mcp_instance" not in (ctx.pkg / "mcp" / "mcp_server.py").read_text()
    assert "get_mcp_instance" not in (ctx.pkg / "mcp" / "__init__.py").read_text()
    ast.parse(new_wrapper)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_g3_deletes_a_main_guard_that_skips_under_pytest(tmp_path: Path) -> None:
    """home-assistant-agent: `if __name__ == "__main__": if "pytest" not in sys.modules: mcp_server()`."""
    server = _server().replace(
        'if __name__ == "__main__":\n    mcp_server()\n',
        'if __name__ == "__main__":\n    if "pytest" not in sys.modules:\n        mcp_server()\n',
    )
    ctx = _repo(tmp_path, server)
    base.RULES["w1.g3"](ctx)
    assert not _blocking(ctx)
    assert "mcp_server" not in (ctx.pkg / "mcp_server.py").read_text()


# --- SDK 0.5.3 hooks (PIPE-GATES-R016.52): registry, action tools, inline tools, routes, readiness, context ---------------
def _texts(ctx: base.Ctx) -> tuple[str, str]:
    """The migrated mcp_server.py and package __init__.py; both must still parse."""
    server = (ctx.pkg / "mcp_server.py").read_text(encoding="utf-8")
    init = (ctx.pkg / "__init__.py").read_text(encoding="utf-8")
    ast.parse(server)
    ast.parse(init)
    return server, init


FAN_REGISTRY = (
    "\ndef register_fan_control_tools(mcp):\n    return None\n\n\n"
    'TOOL_REGISTRY = [("fan-control", "FAN_CONTROLTOOL", register_fan_control_tools)]\n'
)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_tool_registry_with_a_hyphenated_tag_becomes_connector_tool_registry(tmp_path: Path) -> None:
    """fan-manager: a module-level TOOL_REGISTRY whose tag and toggle the SDK cannot derive from the function name."""
    server = _server(top=FAN_REGISTRY, surface=CLIENT + "        tool_registry=TOOL_REGISTRY,\n")
    ctx = _repo(tmp_path, server)
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert "tool_registry=tuple(TOOL_REGISTRY)," in init and "tools=" not in init
    assert "from demo_mcp.mcp_server import TOOL_REGISTRY" in init
    assert "TOOL_REGISTRY" in _texts(ctx)[0]


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_literal_registry_written_in_the_bootstrap_is_inlined(tmp_path: Path) -> None:
    """data-science-mcp: `tool_registry = [...]` inside get_mcp_instance with a lazily imported registrar."""
    before = (
        HEALTH
        + "    from demo_mcp.mcp.zones import register_zones_tools\n\n"
        + '    tool_registry = [\n        ("zones-a", "ZONESTOOL", register_zones_tools),\n'
        + '        ("things", "THINGSTOOL", register_things_tools),\n    ]\n'
    )
    ctx = _repo(
        tmp_path,
        _server(before=before, surface=CLIENT + "        tool_registry=tool_registry,\n"),
        {"demo_mcp/mcp/zones.py": "def register_zones_tools(mcp):\n    return None\n"},
    )
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert (
        'tool_registry=(("zones-a", "ZONESTOOL", register_zones_tools), ("things", "THINGSTOOL", register_things_tools),),'
        in init
    )
    assert "from demo_mcp.mcp.zones import register_zones_tools" in init
    assert "from demo_mcp.mcp_server import register_things_tools" in init
    _texts(ctx)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_imported_registry_with_underived_tags_becomes_a_tuple_of_the_import(tmp_path: Path) -> None:
    """ciso-assistant-api, github-agent: `from <pkg>.mcp import TOOL_REGISTRY` with hyphenated tags."""
    registry = (
        "from demo_mcp.mcp.a import register_a_tools\n\n"
        'TOOL_REGISTRY = [("analytics-metrology", "ANALYTICS_METROLOGYTOOL", register_a_tools)]\n'
    )
    top = "from demo_mcp.mcp import TOOL_REGISTRY\n"
    server = _server(top=top, surface=CLIENT + "        tool_registry=TOOL_REGISTRY,\n")
    ctx = _repo(tmp_path, server, {"demo_mcp/mcp/__init__.py": registry, "demo_mcp/mcp/a.py": ""})
    init = _migrate(ctx)
    assert "tool_registry=tuple(TOOL_REGISTRY)," in init and "from demo_mcp.mcp import TOOL_REGISTRY" in init
    assert "tools=" not in init


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_registry_that_is_not_a_literal_stays_refused(tmp_path: Path) -> None:
    server = _server(top="TOOL_REGISTRY = build()\n", surface=CLIENT + "        tool_registry=TOOL_REGISTRY,\n")
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "not a literal list" in _refused_untouched(ctx, server)


ACTION_IMPORT = "from demo_mcp.action_split import register_split_action_tools\n"
ACTION_MODULE = "def register_split_action_tools(mcp, entries, prefixes=None):\n    return []\n"
ACTION_CALL = """    registered_tags += register_split_action_tools(
        mcp,
        [
            ("remote", "REMOTETOOL", register_things_tools),
            ("files", "FILETOOL", register_files_tools),
        ],
        prefixes={"tm_remote": "tm_remote", "tm_files": "tm_file"},
    )
"""


def _action_server(after: str = ACTION_CALL, top: str = "") -> str:
    return _server(
        top=ACTION_IMPORT + top + "\n\ndef register_files_tools(mcp):\n    return None\n",
        after=after,
        tags="registered_tags = ",
        ret="mcp, args, middlewares, registered_tags",
    )


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_register_split_action_tools_becomes_action_tools_and_prefixes(tmp_path: Path) -> None:
    """tunnel-manager: the package's own action_split module is replaced by Connector(action_tools=...)."""
    ctx = _repo(tmp_path, _action_server(), {"demo_mcp/action_split.py": ACTION_MODULE})
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert (
        'action_tools=(("remote", "REMOTETOOL", register_things_tools), ("files", "FILETOOL", register_files_tools),),'
        in init
    )
    assert 'action_prefixes={"tm_remote": "tm_remote", "tm_files": "tm_file"},' in init
    assert "register_split_action_tools" not in _texts(ctx)[0]
    assert not (ctx.pkg / "action_split.py").exists() and "demo_mcp/action_split.py" in ctx.deleted


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_action_split_module_stays_when_a_test_still_imports_it(tmp_path: Path) -> None:
    files = {
        "demo_mcp/action_split.py": ACTION_MODULE,
        "tests/test_split.py": "from demo_mcp.action_split import register_split_action_tools\n",
    }
    ctx = _repo(tmp_path, _action_server(), files)
    _migrate(ctx)
    assert (ctx.pkg / "action_split.py").exists()
    assert any("stays" in i["detail"] for i in ctx.review.items if not i["blocking"])


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_serve_action_tools_in_a_tags_guard_and_a_surface_free_bootstrap(tmp_path: Path) -> None:
    """data-science-mcp: `if serve_action_tools(mcp, [...]): registered_tags.append("quant")` after a local import."""
    after = (
        "    from demo_mcp.action_tools import serve_action_tools\n\n"
        '    if serve_action_tools(mcp, [("quant", "QUANTTOOL", register_files_tools)]):\n'
        '        registered_tags.append("quant")\n'
    )
    server = _action_server(after=after).replace(ACTION_IMPORT, "")
    ctx = _repo(tmp_path, server, {"demo_mcp/action_tools.py": "def serve_action_tools(mcp, entries):\n    return 1\n"})
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert 'action_tools=(("quant", "QUANTTOOL", register_files_tools),),' in init and "action_prefixes" not in init
    assert not (ctx.pkg / "action_tools.py").exists()


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_action_registration_without_a_tool_surface_declares_no_client(tmp_path: Path) -> None:
    """vector-mcp: no register_tool_surface at all, only `register_split_action_tools(mcp, [...], prefixes={...})`."""
    server = (
        HEAD % ACTION_IMPORT
        + """

def register_files_tools(mcp):
    return None


def get_mcp_instance() -> tuple[Any, ...]:
    load_config()
    args, mcp, middlewares = create_mcp_server(name="demo MCP", version=__version__, instructions="Demo.")

    register_split_action_tools(
        mcp,
        [("files", "FILETOOL", register_files_tools)],
        prefixes={"demo_files": "demo"},
    )

    for mw in middlewares:
        mcp.add_middleware(mw)
    return mcp, args, middlewares
"""
    )
    ctx = _repo(tmp_path, server, {"demo_mcp/action_split.py": ACTION_MODULE})
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert "api=" not in init and 'action_prefixes={"demo_files": "demo"},' in init


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_action_registration_from_outside_the_package_is_refused(tmp_path: Path) -> None:
    server = _action_server().replace(ACTION_IMPORT, "from elsewhere import register_split_action_tools\n")
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "not imported from a module of this package" in _refused_untouched(ctx, server)


INLINE_TOOLS = '''
    @mcp.tool(name="download_media")
    async def download_media(video_url: str = Field(description="URL")) -> dict:
        """Download."""
        return {"url": video_url, "log": logger is not None}

    @mcp.tool
    def watch_media(video_url: str) -> str:
        return video_url
'''


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_inline_tools_are_hoisted_and_declared(tmp_path: Path) -> None:
    """media-downloader: `@mcp.tool(name=...)` functions written inside get_mcp_instance."""
    server = _server(top="from pydantic import Field\n", before=HEALTH + INLINE_TOOLS)
    ctx = _repo(tmp_path, server)
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert "inline_tools=(download_media, watch_media)," in init
    assert "from demo_mcp.mcp_server import download_media" in init
    text, _ = _texts(ctx)
    assert '@tool(name="download_media")\nasync def download_media(' in text and "\n@tool\ndef watch_media" in text
    assert "from fastmcp.tools import tool" in text and "from pydantic import Field" in text
    assert "get_mcp_instance" not in text


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_inline_tool_that_reads_the_server_is_refused(tmp_path: Path) -> None:
    tool = "\n    @mcp.tool\n    def peek() -> int:\n        return len(args.transport) + len(middlewares)\n"
    server = _server(before=HEALTH + tool)
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "reads `args` from the bootstrap" in _refused_untouched(ctx, server)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_inline_tool_calling_another_inline_tool_is_refused(tmp_path: Path) -> None:
    tool = "\n    @mcp.tool\n    def one() -> int:\n        return 1\n\n    @mcp.tool\n    def two() -> int:\n        return one()\n"
    server = _server(before=HEALTH + tool)
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "reads `one` from the bootstrap" in _refused_untouched(ctx, server)


PROBE = """
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        \"\"\"Probe the broker.\"\"\"
        try:
            import confluent_kafka.admin  # noqa: F401
        except ImportError as exc:
            return JSONResponse({"status": "OK", "backend": "unverified", "reason": f"missing: {exc}"})
        try:
            result = get_client().list_topics(timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"status": "degraded", "backend": "unreachable", "error": str(exc)}, status_code=503)
        return JSONResponse({"status": "OK", "backend": "reachable", "topics": len(result)})
"""


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_health_route_that_probes_the_backend_becomes_readiness(tmp_path: Path) -> None:
    """kafka-mcp, documentdb-mcp: a 503 response is not ready, any other is; no exception text is served."""
    ctx = _repo(tmp_path, _server(before=PROBE))
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert "readiness=readiness," in init and "from demo_mcp.mcp_server import readiness" in init
    text, _ = _texts(ctx)
    assert "async def readiness() -> Readiness:" in text and "custom_route" not in text
    assert 'return Readiness(True, {"backend": "unverified"})' in text
    assert 'return Readiness(False, {"backend": "unreachable"})' in text
    assert 'return Readiness(True, {"backend": "reachable", "topics": len(result)})' in text
    assert "str(exc)" not in text and "from agent_connector_sdk.connector_hooks import Readiness" in text
    assert any("/ready" in i["detail"] for i in ctx.review.items if not i["blocking"])


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_ready_route_becomes_readiness_beside_the_plain_health_route(tmp_path: Path) -> None:
    """sql-mcp: a `/ready` route that calls the client."""
    ready = """
    @mcp.custom_route("/ready", methods=["GET"])
    async def readiness_check(request: Request) -> JSONResponse:
        try:
            get_client()
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ready"})
"""
    ctx = _repo(tmp_path, _server(before=HEALTH + ready))
    init = _migrate(ctx)
    assert not _blocking(ctx)
    text, _ = _texts(ctx)
    assert "return Readiness(False)" in text and "return Readiness(True)" in text and "readiness=readiness," in init


@pytest.mark.spec("PIPE-GATES-R016.52")
@pytest.mark.parametrize(
    ("probe", "reason"),
    [
        (PROBE.replace("status_code=503", "status_code=500"), "status other than 200 or 503"),
        (PROBE.replace('"topics": len(result)', '"topics": request.url'), "reads its request"),
        (
            PROBE.replace("async def", "def").replace("return JSONResponse(", "return Response("),
            "not an async function",
        ),
        (PROBE.replace("JSONResponse({", "make({"), "returns something other than"),
    ],
    ids=["status-500", "reads-request", "sync-handler", "not-a-json-response"],
)
def test_probe_that_cannot_be_expressed_as_readiness_is_refused(tmp_path: Path, probe: str, reason: str) -> None:
    server = _server(before=probe)
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert reason in _refused_untouched(ctx, server)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_two_backend_probes_are_refused(tmp_path: Path) -> None:
    ready = PROBE.replace('"/health"', '"/ready"').replace("health_check", "ready_check")
    server = _server(before=PROBE + ready)
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "second backend probe" in _refused_untouched(ctx, server)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_other_custom_route_becomes_a_declared_route(tmp_path: Path) -> None:
    metrics = """
    @mcp.custom_route("/metrics", methods=["GET", "HEAD"], name="metrics")
    async def metrics_route(request: Request) -> JSONResponse:
        return JSONResponse({"up": 1})
"""
    ctx = _repo(tmp_path, _server(before=HEALTH + metrics))
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert 'routes=(Route("/metrics", metrics_route, methods=("GET", "HEAD"), name="metrics"),),' in init
    assert "from agent_connector_sdk.connector_hooks import Route" in init
    text, _ = _texts(ctx)
    assert "\nasync def metrics_route(request: Request) -> JSONResponse:\n" in text and "custom_route" not in text


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_route_with_other_custom_route_keywords_is_refused(tmp_path: Path) -> None:
    route = HEALTH.replace('"/health", methods=["GET"]', '"/metrics", methods=["GET"], include_in_schema=False')
    server = _server(before=route)
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "keywords other than methods and name" in _refused_untouched(ctx, server)


PROMPTS = '''

def register_prompts(mcp: FastMCP):
    """Prompts."""

    @mcp.prompt
    def hello() -> str:
        return "hello"
'''


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_local_one_parameter_registration_takes_the_registration_context(tmp_path: Path) -> None:
    """audio-transcriber, media-downloader, servicenow-api: `register_prompts(mcp: FastMCP)` is rewritten in place."""
    server = _server(top="from fastmcp import FastMCP\n" + PROMPTS, after="    register_prompts(mcp)\n")
    ctx = _repo(tmp_path, server)
    init = _migrate(ctx)
    assert not _blocking(ctx)
    text, _ = _texts(ctx)
    assert 'def register_prompts(context: RegistrationContext):\n    """Prompts."""\n    mcp = context.server\n' in text
    assert "from agent_connector_sdk.connector_hooks import RegistrationContext" in text and "FastMCP" not in text
    assert "extra_registrations=(register_prompts,)," in init and "_register_prompts" not in init


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_local_registration_function_used_elsewhere_gets_an_adapter_instead(tmp_path: Path) -> None:
    server = _server(top=PROMPTS, after="    register_prompts(mcp)\n")
    files = {"tests/test_prompts.py": "from demo_mcp.mcp_server import register_prompts\n"}
    ctx = _repo(tmp_path, server, files)
    init = _migrate(ctx)
    text, _ = _texts(ctx)
    assert "def register_prompts(mcp: FastMCP)" in text or "def register_prompts(mcp)" in text
    assert "extra_registrations=(_register_prompts,)," in init
    assert "    register_prompts(context.server)" in init


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_calls_with_other_arguments_become_one_register_extras(tmp_path: Path) -> None:
    """webarchiver, container-manager-mcp: `f(mcp, lambda: ...)` and `g(registered_tools(mcp))`."""
    top = "from demo_mcp.web import Source, register_web_tools\nfrom demo_mcp.introspect import registered_tools\n"
    after = "    register_web_tools(mcp, lambda: Source(get_client().fetcher))\n    registered_tools(mcp)\n"
    files = {
        "demo_mcp/web.py": "class Source:\n    pass\n\n\ndef register_web_tools(mcp, factory):\n    return None\n",
        "demo_mcp/introspect.py": "def registered_tools(mcp):\n    return {}\n",
    }
    ctx = _repo(tmp_path, _server(top=top, after=after), files)
    init = _migrate(ctx)
    assert not _blocking(ctx)
    assert "extra_registrations=(_register_extras,)," in init
    assert (
        "def _register_extras(context: RegistrationContext) -> None:\n"
        "    register_web_tools(context.server, lambda: Source(get_client().fetcher))\n"
        "    registered_tools(context.server)\n"
    ) in init
    assert "from demo_mcp.web import Source, register_web_tools" in init or "import Source" in init
    ast.parse(init)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_extra_call_reading_a_bootstrap_local_is_refused(tmp_path: Path) -> None:
    top = "from demo_mcp.web import register_web_tools\n"
    server = _server(top=top, after="    register_web_tools(mcp, args)\n")
    ctx = _repo(tmp_path, server, {"demo_mcp/web.py": "def register_web_tools(mcp, args):\n    return None\n"})
    _migrate(ctx)
    assert "reads the bootstrap local `args`" in _refused_untouched(ctx, server)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_registration_before_the_tool_surface_is_refused(tmp_path: Path) -> None:
    """owncast-agent: `register_kg_tools(mcp)` runs before register_tool_surface; the SDK runs it after."""
    top = "from demo_mcp.kg import register_kg_tools\n"
    server = _server(top=top, before=HEALTH + "    register_kg_tools(mcp)\n", tags="registered_tags = ")
    ctx = _repo(tmp_path, server, {"demo_mcp/kg.py": "def register_kg_tools(mcp):\n    return None\n"})
    _migrate(ctx)
    assert "registers the tool surface after other registrations" in _refused_untouched(ctx, server)


CONTENT_HEAD = """    from pathlib import Path

    from agent_connector_sdk.mcp.content import ConnectorContent

    package_root = Path(__file__).resolve().parent
"""


def _content_server(root: str = "", name: str = "demo-mcp") -> str:
    server = _server().replace(
        "    args, mcp, middlewares = create_mcp_server(",
        CONTENT_HEAD.replace("parent\n", f"parent{root}\n") + "    args, mcp, middlewares = create_mcp_server(",
    )
    return server.replace(
        'instructions="Demo server.",',
        'instructions="Demo server.",\n        content=ConnectorContent(\n'
        f'            connector="{name}", package_root=package_root, package_version=__version__\n        ),',
    )


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_content_that_restates_the_convention_is_dropped(tmp_path: Path) -> None:
    """archivebox-api: ConnectorContent of the package directory under the fleet name is the SDK default."""
    ctx = _repo(tmp_path, _content_server())
    init = _migrate(ctx)
    assert not _blocking(ctx) and "content_root" not in init
    assert not [i for i in ctx.review.items if "content was filed" in i["detail"]]


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_content_under_a_subdirectory_becomes_content_root(tmp_path: Path) -> None:
    ctx = _repo(tmp_path, _content_server(root=' / "content"'))
    init = _migrate(ctx)
    assert not _blocking(ctx) and 'content_root="content",' in init


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_content_under_another_connector_name_is_noted_for_review(tmp_path: Path) -> None:
    ctx = _repo(tmp_path, _content_server(name="demo-other"))
    _migrate(ctx)
    assert not _blocking(ctx)
    assert any("'demo-other'" in i["detail"] for i in ctx.review.items if not i["blocking"])


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_content_that_is_not_the_package_directory_is_refused(tmp_path: Path) -> None:
    server = _content_server(root=' / ".." / "x"')
    ctx = _repo(tmp_path, server)
    _migrate(ctx)
    assert "package_root" in _refused_untouched(ctx, server)


@pytest.mark.spec("PIPE-GATES-R016.52")
def test_discovered_registrars_stay_listed_so_the_unused_import_tidy_keeps_them(tmp_path: Path) -> None:
    """sql-mcp: `registrars=[register_sql_tools]` is imported only for the bootstrap; discovery reads the namespace."""
    top = "from demo_mcp.mcp.zones import register_zones_tools\n"
    server = _server(top=top, surface=CLIENT + "        registrars=[register_zones_tools],\n").replace(
        "\ndef register_things_tools(mcp):\n    return None\n", ""
    )
    ctx = _repo(tmp_path, server, {"demo_mcp/mcp/zones.py": "def register_zones_tools(mcp):\n    return None\n"})
    init = _migrate(ctx)
    text, _ = _texts(ctx)
    assert 'tools="demo_mcp.mcp_server"' in init
    assert "from demo_mcp.mcp.zones import register_zones_tools" in text
    assert '__all__ = ["register_zones_tools"]' in text
