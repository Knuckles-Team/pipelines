"""Wave 1 rules: server bootstrap, scaffold tests, version, ingest declaration, entry points (PIPE-GATES-R016.50-.67).

Source: ``plans/connector-sdk-wave1-codemod-rules-2026-10-23.md``. Every rule requires the full pre-migration shape and
otherwise records a review item and leaves the files untouched. ``ORDER`` is the run order; ``ORDER_LAST`` runs after
the ingest rules (the scaffold tests are fingerprinted last so rewritten imports are final).
"""

from __future__ import annotations

import ast
import builtins
import copy
import difflib
import hashlib
import inspect
import json
import re
import tomllib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, TypeGuard

from pipelines_hooks.hygiene.connector_central.base import SDK_PIN, Ctx, rule

ORDER: tuple[str, ...] = (
    "w1.g3",
    "w1.g4",
    "w1.g5",
    "w1.g6",
    "w1.g1",
    "w1.g2",
    "w1.k1",
    "w1.k2",
    "w1.k3",
    "w1.k4",
    "w1.i1",
    "w1.i2",
    "w1.l1",
    "w1.l2",
    "w1.l3",
    "w1.l4",
    "w1.g7",
)
ORDER_LAST: tuple[str, ...] = ("w1.h",)

FINGERPRINTS_PATH = Path(__file__).with_name("scaffold_fingerprints.json")
SCAFFOLD_TESTS = (
    "test_default_content_surfaces.py",
    "test_init_dynamics.py",
    "test_startup.py",
    "test_fleet_name.py",
    "test_ontology_parent_link.py",
    "test_ingest_sources.py",
    "test_sdk_centralization.py",
)
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__", ".tox", ".mypy_cache"}
_SURFACE_KWARGS = ("tool_prefix", "verbose_targets", "verbose_register", "result_coercer", "action_dispatch")
_DISPATCH = """\
if args.transport == "stdio":
    mcp.run(transport="stdio")
elif args.transport == "streamable-http":
    mcp.run(transport="streamable-http", host=args.host, port=args.port)
elif args.transport == "sse":
    mcp.run(transport="sse", host=args.host, port=args.port)
else:
    logger.error("Invalid transport", extra={"transport": args.transport})
    sys.exit(1)
"""
_DECLARATION = '''\
def declaration() -> IngestSourceDeclaration:
    """The declaration the server assembles from this module."""
    specs = []
    for item in SOURCES:
        for entry in item["connector_sources"]:
            body = {k: v for k, v in entry.items() if k not in ("tool", "mapping")}
            specs.append(IngestSourceSpec.model_validate({**body, "tools": (entry["tool"],)}))
    return IngestSourceDeclaration.model_validate(
        {
            "connector": CONNECTOR,
            "sources": specs,
            "schema_mappings": SCHEMA_MAPPINGS,
            "resources": RESOURCES,
        }
    )
'''
_HOOK_KWARGS = (
    "action_tools",
    "action_prefixes",
    "inline_tools",
    "routes",
    "readiness",
    "content_root",
    "extra_registrations",
)
_G3_KEY = "_w1_g3"
_G4_NOTES = "_w1_g4_notes"
_G4_FILES = "_w1_g4_files"


# --- text and AST helpers ------------------------------------------------------------------------------------
def _parse(text: str) -> ast.Module | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _span(node: ast.stmt) -> tuple[int, int]:
    start = node.lineno
    for d in getattr(node, "decorator_list", ()):
        start = min(start, d.lineno)
    return start, node.end_lineno or node.lineno


def _delete_spans(text: str, spans: Iterable[tuple[int, int]]) -> str:
    lines = text.split("\n")
    for start, end in sorted(set(spans), reverse=True):
        a = start - 1
        del lines[a:end]
        i = a
        while 2 <= i < len(lines) and not lines[i].strip() and not lines[i - 1].strip() and not lines[i - 2].strip():
            del lines[i]
        if a == 0:
            while lines and not lines[0].strip():
                del lines[0]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def _replace_span(text: str, start: int, end: int, new: str) -> str:
    lines = text.split("\n")
    lines[start - 1 : end] = new.split("\n") if new else []
    return "\n".join(lines)


def _doc(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _name_loads(nodes: Iterable[ast.AST]) -> set[str]:
    return {n.id for root in nodes for n in ast.walk(root) if isinstance(n, ast.Name)}


def _referenced(tree: ast.Module) -> set[str]:
    names = _name_loads([tree])
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            names |= {e.value for e in ast.walk(node.value) if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return names


def _import_text(node: ast.stmt, aliases: list[ast.alias]) -> str:
    def one(a: ast.alias) -> str:
        return f"{a.name} as {a.asname}" if a.asname else a.name

    if isinstance(node, ast.ImportFrom):
        head = f"from {'.' * node.level}{node.module or ''} import "
        one_line = head + ", ".join(one(a) for a in aliases)
        if len(one_line) <= 88:
            return one_line
        return head + "(\n" + "".join(f"    {one(a)},\n" for a in aliases) + ")"
    return "import " + ", ".join(one(a) for a in aliases)


def _bound(a: ast.alias, node: ast.stmt) -> str:
    if a.asname:
        return a.asname
    return a.name if isinstance(node, ast.ImportFrom) else a.name.split(".")[0]


def _prune_imports(text: str, candidates: set[str]) -> str:
    """Remove top-level import names in ``candidates`` that nothing in the module references any more."""
    tree = _parse(text)
    if tree is None or not candidates:
        return text
    used = _referenced(tree)
    edits: list[tuple[int, int, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.Import | ast.ImportFrom) or getattr(node, "module", "") == "__future__":
            continue
        keep = [a for a in node.names if a.name == "*" or _bound(a, node) not in candidates or _bound(a, node) in used]
        if len(keep) == len(node.names):
            continue
        edits.append((node.lineno, node.end_lineno or node.lineno, _import_text(node, keep) if keep else ""))
    for start, end, new in sorted(edits, reverse=True):
        if new:
            text = _replace_span(text, start, end, new)
        else:
            text = _delete_spans(text, [(start, end)])
    return text


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if not (set(p.relative_to(root).parts) & _SKIP_DIRS))


def _declared(ctx: Ctx) -> bool:
    init = ctx.pkg / "__init__.py"
    tree = _parse(init.read_text(encoding="utf-8")) if init.is_file() else None
    if tree is None:
        return False
    return any(
        isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "connector" for t in n.targets)
        for n in tree.body
    )


def _top_defs(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for n in tree.body:
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            out |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
    return out


def _src(node: ast.expr) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return json.dumps(node.value, ensure_ascii=False)
    return ast.unparse(node)


# --- g.3 mcp_server.py split --------------------------------------------------------------------------------
class _Reject(Exception):
    pass


def _pos(node: ast.expr) -> tuple[int, int, int, int]:
    """Start/end line and column of a node parsed from source (end positions are always set)."""
    assert node.end_lineno is not None and node.end_col_offset is not None
    return node.lineno, node.col_offset, node.end_lineno, node.end_col_offset


def _expr_of(src: str) -> ast.expr:
    """Parse a constant one-expression source snippet and return that expression."""
    stmt = ast.parse(src).body[0]
    assert isinstance(stmt, ast.Expr)
    return stmt.value


def _is_call(node: ast.AST, name: str) -> TypeGuard[ast.Call]:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name


_ENV_KEYS = ("FASTMCP_LOG_LEVEL", "TERM", "NO_COLOR")


def _env_key(stmt: ast.stmt) -> str | None:
    """The key of an allowed `os.environ["KEY"] = "<const str>"` statement, else None."""
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1):
        return None
    t, v = stmt.targets[0], stmt.value
    if not (isinstance(t, ast.Subscript) and ast.dump(t.value) == ast.dump(_expr_of("os.environ"))):
        return None
    key = t.slice
    if not (isinstance(key, ast.Constant) and key.value in _ENV_KEYS):
        return None
    return str(key.value) if isinstance(v, ast.Constant) and isinstance(v.value, str) else None


def _bare_call(stmt: ast.stmt) -> ast.Call | None:
    return stmt.value if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) else None


def _one_param(fn: ast.FunctionDef) -> bool:
    a = fn.args
    return len(a.args) == 1 and not (a.posonlyargs or a.vararg or a.kwonlyargs or a.kwarg)


_REGISTRAR = re.compile(r"register_(.+)_tools")
_TRANSPORTS = ("stdio", "streamable-http", "sse")
_LOG_METHODS = ("debug", "info", "warning", "error")


@dataclass
class _Env:
    """What the g.3 analysis knows about the module around ``get_mcp_instance``."""

    ctx: Ctx
    tree: ast.Module
    imports: dict[str, tuple[str, str] | None]
    module: str = ""
    local_assigns: dict[str, ast.expr] = field(default_factory=dict)


def _bad(stmt: ast.stmt, why: str = "is outside the allowed bootstrap statements") -> _Reject:
    return _Reject(f"line {stmt.lineno}: `{ast.unparse(stmt)[:70]}` {why}")


def _bound_names(tree: ast.Module) -> set[str]:
    names = _top_defs(tree)
    for n in tree.body:
        if isinstance(n, ast.Import | ast.ImportFrom):
            names |= {_bound(a, n) for a in n.names}
    return names


def _module_file(ctx: Ctx, dotted: str) -> Path | None:
    """The source file of ``dotted`` when it is a module of this package, else None."""
    if dotted.split(".")[0] != ctx.pkg_name:
        return None
    base = ctx.root / dotted.replace(".", "/")
    for cand in (base.with_suffix(".py"), base / "__init__.py"):
        if cand.is_file():
            return cand
    return None


def _package_module(ctx: Ctx, imports: dict[str, tuple[str, str] | None], name: str) -> str | None:
    """The dotted module a plain name is bound to by an import, when that module lives in this package."""
    hit = imports.get(name)
    if not hit:
        return None
    mod, orig = hit
    if orig:
        dotted = f"{mod}.{orig}"
    elif name == mod or ("." in mod and name != mod.split(".")[0]):
        dotted = mod
    else:
        return None
    return dotted if _module_file(ctx, dotted) else None


def _registry_rows(entries: ast.expr) -> list[tuple[str, str, str]]:
    """The ``(tag, toggle, function name)`` rows of a literal registry, else _Reject."""
    if not isinstance(entries, ast.List | ast.Tuple):
        raise _Reject("the tool registry is not a literal list")
    rows: list[tuple[str, str, str]] = []
    for e in entries.elts:
        parts = e.elts if isinstance(e, ast.Tuple) else []
        if not (
            len(parts) == 3
            and isinstance(parts[0], ast.Constant)
            and isinstance(parts[0].value, str)
            and isinstance(parts[1], ast.Constant)
            and isinstance(parts[1].value, str)
            and isinstance(parts[2], ast.Name)
        ):
            raise _Reject("a tool registry entry is not a literal (tag, toggle, function name)")
        rows.append((parts[0].value, parts[1].value, parts[2].id))
    return rows


def _derived(rows: list[tuple[str, str, str]]) -> bool:
    """Whether SDK discovery derives every tag and toggle from the ``register_<tag>_tools`` name."""
    for tag, toggle, fn in rows:
        found = _REGISTRAR.fullmatch(fn)
        if not found or found.group(1) != tag or toggle != tag.upper() + "TOOL":
            return False
    return True


def _check_discovery(fns: set[str], ns: set[str]) -> None:
    """The module namespace must hold exactly the registrars, since the SDK registers every `register_*_tools`."""
    missing = sorted(fns - ns)
    if missing:
        raise _Reject(f"registrar {missing[0]} is not bound at module level, so SDK discovery would not find it")
    extra = sorted(n for n in ns - fns if _REGISTRAR.fullmatch(n))
    if extra:
        raise _Reject(f"the module also binds {extra[0]}, which SDK discovery would register as well")


def _tools_target(
    stmt: ast.stmt, kw: dict[str, ast.expr], env: _Env, imports: dict[str, tuple[str, str] | None]
) -> dict[str, Any]:
    """Resolve how register_tool_surface finds its registrar tools: the module to name in ``Connector(tools=...)``."""
    own = env.module
    sources = [k for k in ("tools_module", "tool_registry", "registrars") if k in kw]
    if len(sources) > 1:
        raise _bad(stmt, f"passes {' and '.join(sources)}; the SDK honours exactly one")
    ns = _bound_names(env.tree)
    out: dict[str, Any] = {"tools": None, "keep": set()}
    if not sources:
        return out
    node = kw[sources[0]]
    if sources[0] == "tools_module":
        if ast.dump(node) == ast.dump(_expr_of("sys.modules[__name__]")):
            out["tools"] = own
        else:
            mod = _package_module(env.ctx, imports, node.id) if isinstance(node, ast.Name) else None
            if mod is None:
                raise _bad(
                    stmt, "passes a tools_module that is neither sys.modules[__name__] nor a module of this package"
                )
            out["tools"] = mod
    elif sources[0] == "registrars":
        if not (isinstance(node, ast.List | ast.Tuple) and all(isinstance(e, ast.Name) for e in node.elts)):
            raise _bad(stmt, "passes registrars that are not a literal list of plain names")
        names = {e.id for e in node.elts if isinstance(e, ast.Name)}
        bad = sorted(n for n in names if not _REGISTRAR.fullmatch(n))
        if bad:
            raise _bad(stmt, f"passes registrar {bad[0]}, whose name is not register_<tag>_tools")
        try:
            _check_discovery(names, ns)
        except _Reject as err:
            raise _bad(stmt, str(err)) from None
        out["tools"], out["keep"], out["ordered"] = own, names, True
    else:
        out.update(_registry_target(stmt, node, env, imports, ns))
    return out


def _registry_target(
    stmt: ast.stmt, node: ast.expr, env: _Env, imports: dict[str, tuple[str, str] | None], ns: set[str]
) -> dict[str, Any]:
    """A registry the SDK derives by name becomes discovery; any other becomes ``Connector(tool_registry=...)``."""
    if not isinstance(node, ast.Name):
        raise _bad(stmt, "passes a tool_registry that is not a plain name")
    own = env.module
    assigns = {
        t.id: n.value for n in env.tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)
    }
    try:
        if node.id in env.local_assigns:  # a literal written inside the bootstrap
            return {"tools": None, "keep": set(), "registry": {"rows": _registry_rows(env.local_assigns[node.id])}}
        if node.id in assigns:
            rows = _registry_rows(assigns[node.id])
            if not _derived(rows):
                return {"tools": None, "keep": set(), "registry": {"name": node.id}}
            _check_discovery({fn for _t, _g, fn in rows}, ns)
            return {"tools": own, "keep": {fn for _t, _g, fn in rows}, "ordered": True}
        hit = imports.get(node.id)
        file = _module_file(env.ctx, hit[0]) if hit and hit[1] else None
        if hit is None or file is None:
            raise _Reject("the tool registry is neither defined here nor imported from a module of this package")
        mod = _parse(file.read_text(encoding="utf-8"))
        defs = (
            {t.id: n.value for n in mod.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
            if mod
            else {}
        )
        if hit[1] not in defs:
            raise _Reject(f"{hit[0]} does not define {hit[1]} as a literal list")
        assert mod is not None
        rows = _registry_rows(defs[hit[1]])
        if not _derived(rows):
            return {"tools": None, "keep": set(), "registry": {"name": node.id}}
        _check_discovery({fn for _t, _g, fn in rows}, _bound_names(mod))
        return {"tools": hit[0], "keep": set(), "ordered": True}
    except _Reject as err:
        raise _bad(stmt, str(err)) from None


def _is_health_route(route: ast.FunctionDef | ast.AsyncFunctionDef, mcp_n: str) -> bool:
    d = route.decorator_list[0]
    return (
        len(route.decorator_list) == 1
        and isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.func.attr == "custom_route"
        and isinstance(d.func.value, ast.Name)
        and d.func.value.id == mcp_n
        and bool(d.args)
        and isinstance(d.args[0], ast.Constant)
        and d.args[0].value == "/health"
    )


def _dead_log(stmt: ast.stmt, tags: str | None) -> bool:
    """A logger call or `_ = tags` that reads only the registered-tags value (deleted with the bootstrap)."""
    if (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
        and stmt.targets[0].id == "_"
    ):
        return tags is not None and isinstance(stmt.value, ast.Name) and stmt.value.id == tags
    call = _bare_call(stmt)
    if call is None or not (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "logger"
        and call.func.attr in _LOG_METHODS
    ):
        return False
    allowed = {"logger", tags} if tags else {"logger"}
    return all(n in allowed or hasattr(builtins, n) for n in _name_loads([call]))


def _empty_list_name(stmt: ast.stmt) -> str | None:
    if (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
        and isinstance(stmt.value, ast.List)
        and not stmt.value.elts
    ):
        return stmt.targets[0].id
    return None


def _dead_loop(stmt: ast.stmt, dead: set[str], mcp_n: str) -> bool:
    """`for x in <always-empty list>: mcp.add_tool(x)` (or add_resource)."""
    if not (
        isinstance(stmt, ast.For)
        and isinstance(stmt.target, ast.Name)
        and isinstance(stmt.iter, ast.Name)
        and stmt.iter.id in dead
        and not stmt.orelse
        and len(stmt.body) == 1
    ):
        return False
    return any(
        ast.dump(stmt.body[0]) == ast.dump(ast.parse(f"{mcp_n}.{m}({stmt.target.id})").body[0])
        for m in ("add_tool", "add_resource")
    )


def _inert_openapi(stmt: ast.stmt, args_n: str) -> bool:
    """`if getattr(args, "openapi_file", None): ...` — the SDK parser defines no such flag, so it never runs."""
    return (
        isinstance(stmt, ast.If)
        and not stmt.orelse
        and ast.dump(stmt.test) == ast.dump(_expr_of(f'getattr({args_n}, "openapi_file", None)'))
    )


def _forwards_command_args(fn: ast.FunctionDef, value: ast.expr) -> bool:
    """``command_args=command_args`` (or ``[] if command_args is None else command_args``) of the function's own parameter."""
    params = {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs]}
    if "command_args" not in params:
        return False
    plain = isinstance(value, ast.Name) and value.id == "command_args"
    guarded = ast.dump(value) == ast.dump(_expr_of("[] if command_args is None else command_args"))
    return plain or guarded


def _custom_route(dec: ast.expr, mcp_n: str) -> ast.Call | None:
    """``@mcp.custom_route(...)`` decorator call, else None."""
    if (
        isinstance(dec, ast.Call)
        and isinstance(dec.func, ast.Attribute)
        and dec.func.attr == "custom_route"
        and isinstance(dec.func.value, ast.Name)
        and dec.func.value.id == mcp_n
    ):
        return dec
    return None


def _tool_decorator(dec: ast.expr, mcp_n: str) -> ast.Attribute | None:
    """The ``mcp.tool`` attribute of ``@mcp.tool`` / ``@mcp.tool(...)``, else None."""
    target = dec.func if isinstance(dec, ast.Call) else dec
    if (
        isinstance(target, ast.Attribute)
        and target.attr == "tool"
        and isinstance(target.value, ast.Name)
        and target.value.id == mcp_n
    ):
        return target
    return None


def _route_spec(s: ast.FunctionDef | ast.AsyncFunctionDef, route: ast.Call) -> dict[str, Any]:
    """``{path, methods, name}`` of a ``custom_route`` decorator that only passes literals, else _Reject."""
    if len(route.args) != 1 or not (isinstance(route.args[0], ast.Constant) and isinstance(route.args[0].value, str)):
        raise _bad(s, "is a custom route whose path is not a single string literal")
    kws = {k.arg: k.value for k in route.keywords}
    if None in kws or set(kws) - {"methods", "name"}:
        raise _bad(s, "is a custom route with keywords other than methods and name")
    methods = kws.get("methods")
    if not (
        isinstance(methods, ast.List | ast.Tuple)
        and methods.elts
        and all(isinstance(m, ast.Constant) and isinstance(m.value, str) for m in methods.elts)
    ):
        raise _bad(s, "is a custom route whose methods are not a literal list of strings")
    name = kws.get("name")
    if name is not None and not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
        raise _bad(s, "is a custom route whose name is not a string literal")
    return {
        "path": route.args[0].value,
        "methods": tuple(str(m.value) for m in methods.elts if isinstance(m, ast.Constant)),
        "name": name.value if isinstance(name, ast.Constant) else None,
        "node": s,
    }


def _pre_function(s: ast.FunctionDef | ast.AsyncFunctionDef, info: dict[str, Any], mcp_n: str) -> None:
    """Classify a decorated function written inside the bootstrap: /health, readiness, a route or an inline tool."""
    if len(s.decorator_list) != 1:
        raise _bad(s, "has several decorators")
    dec = s.decorator_list[0]
    route = _custom_route(dec, mcp_n)
    if route is not None:
        spec = _route_spec(s, route)
        rbody = [x for x in s.body if not _doc(x)]
        if spec["path"] == "/health" and len(rbody) == 1 and isinstance(rbody[0], ast.Return):
            if info["health"]:
                raise _bad(s, "is a second /health route")
            info["health"] = True
        elif spec["path"] in ("/health", "/ready"):
            if info["ready"] is not None:
                raise _bad(s, "is a second backend probe; the SDK serves one /ready")
            info["ready"] = s
            info["ready_path"] = spec["path"]
        else:
            info["routes"].append(spec)
        return
    if _tool_decorator(dec, mcp_n) is not None:
        info["inline"].append(s)
        return
    raise _bad(s, "is decorated by something other than mcp.custom_route or mcp.tool")


def _package_function(ctx: Ctx, imports: dict[str, tuple[str, str] | None], name: str) -> str | None:
    """The dotted module of this package that ``name`` is imported from, else None."""
    hit = imports.get(name)
    if not hit or not hit[1]:
        return None
    return hit[0] if _module_file(ctx, hit[0]) else None


def _action_stmt(
    s: ast.stmt, mcp_n: str, tags: str | None, imports: dict[str, tuple[str, str] | None], ctx: Ctx
) -> dict[str, Any] | None:
    """A ``register_split_action_tools`` / ``serve_action_tools`` statement, else None (_Reject when malformed)."""
    call: ast.expr | None = None
    target: str | None = None
    if isinstance(s, ast.Expr):
        call = s.value
    elif isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
        call, target = s.value, s.targets[0].id
    elif isinstance(s, ast.AugAssign) and isinstance(s.op, ast.Add) and isinstance(s.target, ast.Name):
        call, target = s.value, s.target.id
    elif isinstance(s, ast.If) and not s.orelse and len(s.body) == 1:
        call, target = s.test, tags
        only = s.body[0]
        if not (
            tags is not None
            and isinstance(only, ast.Expr)
            and isinstance(only.value, ast.Call)
            and ast.unparse(only.value.func) == f"{tags}.append"
            and len(only.value.args) == 1
            and isinstance(only.value.args[0], ast.Constant)
        ):
            return None
    if not (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id in ("register_split_action_tools", "serve_action_tools")
    ):
        return None
    fn = call.func.id
    module = _package_function(ctx, imports, fn)
    if module is None:
        raise _bad(s, f"calls `{fn}`, which is not imported from a module of this package")
    if len(call.args) != 2 or not (isinstance(call.args[0], ast.Name) and call.args[0].id == mcp_n):
        raise _bad(s, f"does not pass the server and one literal list of registrars to {fn}")
    kws = {k.arg: k.value for k in call.keywords}
    if None in kws or set(kws) - ({"prefixes"} if fn == "register_split_action_tools" else set()):
        raise _bad(s, f"passes keywords to {fn} that Connector.action_prefixes does not express")
    try:
        rows = _registry_rows(call.args[1])
    except _Reject as err:
        raise _bad(s, str(err)) from None
    prefixes: dict[str, str] = {}
    given = kws.get("prefixes")
    if given is not None:
        if not (
            isinstance(given, ast.Dict)
            and all(
                isinstance(k, ast.Constant)
                and isinstance(k.value, str)
                and isinstance(v, ast.Constant)
                and isinstance(v.value, str)
                for k, v in zip(given.keys, given.values, strict=True)
            )
        ):
            raise _bad(s, f"passes prefixes to {fn} that are not a literal mapping of strings")
        for k, v in zip(given.keys, given.values, strict=True):
            assert isinstance(k, ast.Constant) and isinstance(v, ast.Constant)  # checked above
            prefixes[str(k.value)] = str(v.value)
    return {"rows": rows, "prefixes": prefixes, "module": module, "target": target, "call": call}


def _prelude(body: list[ast.stmt], i: int, info: dict[str, Any]) -> int:
    """Statements before create_mcp_server that only feed ``content=ConnectorContent(...)``; returns the next index."""
    path_names = ("Path", "ConnectorContent")
    while i < len(body):
        s = body[i]
        if (
            isinstance(s, ast.ImportFrom)
            and s.level == 0
            and s.module in ("pathlib", "agent_connector_sdk.mcp.content")
            and all(a.name in path_names and not a.asname for a in s.names)
        ):
            info["prelude_imports"].append(s)
        elif (
            isinstance(s, ast.Assign)
            and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name)
            and isinstance(s.value, ast.Constant)
            and isinstance(s.value.value, str)
        ):
            info["local_consts"][s.targets[0].id] = s.value
        elif (
            isinstance(s, ast.Assign)
            and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name)
            and info.get("package_root") is None
        ):
            rel = _package_root_rel(s.value)
            if rel is None:
                break
            info["package_root"] = (s.targets[0].id, rel[0])
        else:
            break
        i += 1
    return i


def _argv_isolation(body: list[ast.stmt], i: int) -> ast.Assign | None:
    """The 3 statements that isolate ``sys.argv`` around create_mcp_server; the create assignment they wrap, else None.

    ``saved = sys.argv`` / ``if command_args is not None: sys.argv = [saved[0] if saved else "x", *command_args]`` /
    ``try: <create_mcp_server> finally: sys.argv = saved`` is what ``create_mcp_server(command_args=...)`` does.
    """
    if i + 2 >= len(body):
        return None
    save, guard, wrap = body[i : i + 3]
    if not (
        isinstance(save, ast.Assign)
        and len(save.targets) == 1
        and isinstance(save.targets[0], ast.Name)
        and ast.dump(save.value) == ast.dump(_expr_of("sys.argv"))
    ):
        return None
    saved = save.targets[0].id
    argv = ast.parse(f'sys.argv = [{saved}[0] if {saved} else "x", *command_args]').body[0]
    if not (
        isinstance(guard, ast.If)
        and not guard.orelse
        and ast.dump(guard.test) == ast.dump(_expr_of("command_args is not None"))
        and len(guard.body) == 1
        and isinstance(guard.body[0], ast.Assign)
        and isinstance(argv, ast.Assign)
        and ast.dump(guard.body[0].targets[0]) == ast.dump(argv.targets[0])
        and isinstance(guard.body[0].value, ast.List)
        and len(guard.body[0].value.elts) == 2
        and ast.dump(guard.body[0].value.elts[1]) == ast.dump(argv.value.elts[1])  # type: ignore[attr-defined]
        and ast.dump(guard.body[0].value.elts[0].test) == ast.dump(argv.value.elts[0].test)  # type: ignore[attr-defined]
    ):
        return None
    restore = ast.parse(f"sys.argv = {saved}").body[0]
    if not (
        isinstance(wrap, ast.Try)
        and not wrap.handlers
        and not wrap.orelse
        and len(wrap.body) == 1
        and isinstance(wrap.body[0], ast.Assign)
        and len(wrap.finalbody) == 1
        and ast.dump(wrap.finalbody[0]) == ast.dump(restore)
    ):
        return None
    return wrap.body[0]


def _package_root_rel(value: ast.expr) -> tuple[str | None] | None:
    """``Path(__file__).resolve().parent`` -> (None,); ``... / "rel"`` -> ("rel",); anything else None."""
    base = _expr_of("Path(__file__).resolve().parent")
    if ast.dump(value) == ast.dump(base):
        return (None,)
    if (
        isinstance(value, ast.BinOp)
        and isinstance(value.op, ast.Div)
        and ast.dump(value.left) == ast.dump(base)
        and isinstance(value.right, ast.Constant)
        and isinstance(value.right.value, str)
    ):
        rel = value.right.value
        pure = PurePosixPath(rel)
        if rel.strip() and not pure.is_absolute() and ".." not in pure.parts:
            return (rel,)
    return None


def _content_kw(stmt: ast.stmt, value: ast.expr, info: dict[str, Any], fleet: str, consts: dict[str, str]) -> None:
    """``content=ConnectorContent(connector=..., package_root=<package dir>, package_version=__version__)``."""
    root = info.get("package_root")
    ok = (
        root is not None
        and isinstance(value, ast.Call)
        and _is_call(value, "ConnectorContent")
        and not value.args
        and {k.arg for k in value.keywords} == {"connector", "package_root", "package_version"}
    )
    if not (ok and isinstance(value, ast.Call) and root is not None):
        raise _bad(stmt, "passes content= that is not ConnectorContent of the package directory")
    kw = {k.arg: k.value for k in value.keywords}
    name, pkg_root, version = kw["connector"], kw["package_root"], kw["package_version"]
    connector = (
        name.value
        if isinstance(name, ast.Constant) and isinstance(name.value, str)
        else consts.get(name.id)
        if isinstance(name, ast.Name)
        else None
    )
    if not (
        connector is not None
        and isinstance(pkg_root, ast.Name)
        and pkg_root.id == root[0]
        and isinstance(version, ast.Name)
        and version.id == "__version__"
    ):
        raise _bad(stmt, "passes content= that is not ConnectorContent(<string>, <package dir>, __version__)")
    info["content_root"] = root[1]
    if connector != fleet:
        info["content_name"] = connector


def _analyse_instance(fn: ast.FunctionDef, local_funcs: dict[str, ast.FunctionDef], env: _Env) -> dict[str, Any]:
    body = list(fn.body)
    if body and _doc(body[0]):
        body = body[1:]
    info: dict[str, Any] = {
        "health": False,
        "env": [],
        "tags": None,
        "extras": [],
        "inert": False,
        "inline": [],
        "helpers": [],
        "routes": [],
        "ready": None,
        "actions": [],
        "prelude_imports": [],
        "local_consts": {},
        "package_root": None,
        "content_root": None,
        "content_name": None,
    }
    envs = [(s, _env_key(s)) for s in body]
    info["env"] = [k for _s, k in envs if k]
    body = [s for s, k in envs if not k]
    imports = dict(env.imports)
    i = 0

    def bad(stmt: ast.stmt, why: str = "is outside the allowed bootstrap statements") -> _Reject:
        return _bad(stmt, why)

    head = body[i] if i < len(body) else None
    if isinstance(head, ast.Expr) and _is_call(head.value, "load_config"):
        if head.value.args or head.value.keywords:
            raise bad(head)
        i += 1
    i = _prelude(body, i, info)
    isolated = _argv_isolation(body, i)
    if isolated is not None:
        body[i : i + 3] = [isolated]
    if i >= len(body):
        raise _Reject("no create_mcp_server call")
    stmt = body[i]
    if not (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Tuple)
        and len(stmt.targets[0].elts) == 3
        and all(isinstance(e, ast.Name) for e in stmt.targets[0].elts)
        and _is_call(stmt.value, "create_mcp_server")
    ):
        raise bad(stmt)
    assert isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Tuple)  # guaranteed by the check above
    args_n, mcp_n, mw_n = (e.id for e in stmt.targets[0].elts if isinstance(e, ast.Name))
    call = stmt.value
    assert isinstance(call, ast.Call)
    ckw = {k.arg: k.value for k in call.keywords}
    if call.args or None in ckw:
        raise bad(stmt, "passes positional or ** arguments to create_mcp_server")
    extra_kw = set(ckw) - {"name", "version", "instructions", "content"}
    if "command_args" in extra_kw and _forwards_command_args(fn, ckw["command_args"]):
        extra_kw.discard("command_args")  # the SDK's own serve() passes the process arguments
    if isolated is not None:
        if "command_args" not in {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs]}:
            raise bad(stmt, "isolates sys.argv for a command_args parameter the function does not have")
    if extra_kw:
        raise bad(
            stmt,
            f"passes {sorted(str(k) for k in extra_kw)} to create_mcp_server (beyond name, version and instructions)",
        )
    if "content" in ckw:
        consts = {
            t.id: n.value.value
            for n in env.tree.body
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
            for t in n.targets
            if isinstance(t, ast.Name)
        }
        _content_kw(stmt, ckw["content"], info, env.ctx.fleet, consts)
    elif info["package_root"] is not None or info["prelude_imports"]:
        raise bad(stmt, "is preceded by content statements that create_mcp_server does not use")
    version = ckw.get("version")
    if not (isinstance(version, ast.Name) and version.id == "__version__"):
        raise bad(stmt, "does not pass version=__version__")
    if "instructions" not in ckw:
        raise bad(stmt, "has no instructions=")
    info["instructions"] = ckw["instructions"]
    given_ins = ckw["instructions"]
    if isinstance(given_ins, ast.Name) and given_ins.id in info["local_consts"]:
        info["instructions"] = info["local_consts"][given_ins.id]
    info["mcp"], info["args"], info["mw"] = mcp_n, args_n, mw_n
    i += 1
    dead: set[str] = set()
    local_imports: list[ast.ImportFrom] = []
    while i < len(body):  # statements between the server and the surface registration
        s = body[i]
        if isinstance(s, ast.AsyncFunctionDef | ast.FunctionDef) and s.decorator_list:
            _pre_function(s, info, mcp_n)
        elif isinstance(s, ast.AsyncFunctionDef | ast.FunctionDef):
            info["helpers"].append(s)  # a plain helper the hoisted tools share
        elif (name := _empty_list_name(s)) is not None:
            dead.add(name)
        elif _inert_openapi(s, args_n):
            info["inert"] = True
        elif isinstance(s, ast.ImportFrom) and s.level == 0 and not any(a.name == "*" for a in s.names):
            for a in s.names:
                imports[a.asname or a.name] = (s.module or "", a.name)
            local_imports.append(s)
        elif (
            isinstance(s, ast.Assign)
            and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name)
            and s.targets[0].id == "tool_registry"
            and isinstance(s.value, ast.List | ast.Tuple)
        ):
            env.local_assigns["tool_registry"] = s.value
            info["registry_stmt"] = s
        else:
            break
        i += 1
    if i >= len(body):
        raise _Reject("no register_tool_surface call")
    stmt = body[i]
    surface = None
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        if _is_call(stmt.value, "register_tool_surface"):
            info["tags"] = stmt.targets[0].id
            surface = stmt.value
    elif isinstance(stmt, ast.Expr) and _is_call(stmt.value, "register_tool_surface"):
        surface = stmt.value
    used = _name_loads([info["registry_stmt"]]) if "registry_stmt" in info else set()
    if surface is not None:
        if len(surface.args) != 1 or not (isinstance(surface.args[0], ast.Name) and surface.args[0].id == mcp_n):
            raise bad(stmt, "does not pass the server as the only positional argument")
        kw = {k.arg: k.value for k in surface.keywords if k.arg}
        if len(kw) != len(surface.keywords):
            raise bad(stmt, "passes **kwargs to register_tool_surface")
        allowed = {"client_cls", "get_client", "service", "tools_module", "tool_registry", "registrars", "manifest"}
        allowed |= set(_SURFACE_KWARGS)
        if set(kw) - allowed:
            raise bad(stmt, f"passes unsupported keywords {sorted(k for k in kw if k not in allowed)}")
        if ("client_cls" in kw) != ("get_client" in kw):
            raise bad(stmt, "passes only one of client_cls and get_client")
        for need in ("client_cls", "get_client"):
            if need in kw and not isinstance(kw[need], ast.Name):
                raise bad(stmt, f"does not pass {need} as a plain name")
        if "manifest" in kw and "client_cls" not in kw:
            raise bad(stmt, "passes a manifest without a client")
        used |= _name_loads([surface])
        info.update(_tools_target(stmt, kw, env, imports))
        info["surface"] = kw
        i += 1
    else:
        info.update({"tools": None, "keep": set(), "surface": {}})
    while i < len(body):
        s = body[i]
        if _dead_log(s, info["tags"]) or _dead_loop(s, dead, mcp_n):
            i += 1
            continue
        if isinstance(s, ast.ImportFrom) and s.level == 0 and not any(a.name == "*" for a in s.names):
            for a in s.names:
                imports[a.asname or a.name] = (s.module or "", a.name)
            local_imports.append(s)
            i += 1
            continue
        action = _action_stmt(s, mcp_n, info["tags"], imports, env.ctx)
        if action is not None:
            if action["target"] and info["tags"] is None:
                info["tags"] = action["target"]
            elif action["target"] and action["target"] != info["tags"]:
                raise bad(s, "assigns the action registrations to a second name")
            info["actions"].append(action)
            used |= _name_loads([action["call"]])
            i += 1
            continue
        extra = _bare_call(s)
        wrapped = s.value if isinstance(s, ast.Assign | ast.Expr) else None
        if wrapped is not None and _is_call(wrapped, "register_tool_surface"):
            raise bad(s, "registers the tool surface after other registrations; the SDK registers the surface first")
        if extra is None or not isinstance(extra.func, ast.Name) or mcp_n not in _name_loads(extra.args):
            break
        name = extra.func.id
        simple = len(extra.args) == 1 and not extra.keywords and _name_loads(extra.args) == {mcp_n}
        target = local_funcs.get(name)
        if simple:
            if target is None and name in imports:
                pass  # an imported callable is run with the server exactly as `extra_registrations` does
            elif target is None or not _one_param(target):
                raise bad(
                    s,
                    f"calls `{name}`, which is not a top-level function of mcp_server.py taking exactly one parameter",
                )
        info["extras"].append(extra)
        used |= _name_loads([extra])
        i += 1
    if i >= len(body):
        raise _Reject("no middleware loop")
    stmt = body[i]
    loop_ok = (
        isinstance(stmt, ast.For)
        and isinstance(stmt.target, ast.Name)
        and isinstance(stmt.iter, ast.Name)
        and stmt.iter.id == mw_n
        and not stmt.orelse
        and len(stmt.body) == 1
        and isinstance(stmt.body[0], ast.Expr)
        and ast.dump(stmt.body[0].value) == ast.dump(_expr_of(f"{mcp_n}.add_middleware({stmt.target.id})"))
    )
    if not loop_ok:
        raise bad(stmt)
    i += 1
    final = body[i] if i < len(body) else None
    if not isinstance(final, ast.Return) or i != len(body) - 1:
        raise bad(body[min(i, len(body) - 1)], "is not the final return")
    for imp in local_imports:
        if any((a.asname or a.name) not in used for a in imp.names):
            raise bad(imp, "imports a name the registrations do not use")
    info["ret"] = []
    if final.value is not None:
        if not (isinstance(final.value, ast.Tuple) and all(isinstance(e, ast.Name) for e in final.value.elts)):
            raise bad(final)
        info["ret"] = [e.id for e in final.value.elts if isinstance(e, ast.Name)]
    info["imports"] = imports
    info["boot_locals"] = _boot_locals(fn, (args_n, mcp_n, mw_n))
    return info


def _boot_locals(fn: ast.FunctionDef, given: tuple[str, ...]) -> set[str]:
    """Names that exist only inside the bootstrap, so a function hoisted out of it must not read them."""
    names = set(given)
    for s in fn.body:
        if isinstance(s, ast.Assign):
            names |= {n.id for t in s.targets for n in ast.walk(t) if isinstance(n, ast.Name)}
        elif isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(s.name)
        elif isinstance(s, ast.Import | ast.ImportFrom):
            names |= {_bound(a, s) for a in s.names}
        elif isinstance(s, ast.AnnAssign | ast.AugAssign) and isinstance(s.target, ast.Name):
            names.add(s.target.id)
    names |= {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs]}
    return names


def _is_stderr_print(stmt: ast.stmt) -> bool:
    banner_call = _expr_of('print("x", file=sys.stderr)')
    assert isinstance(banner_call, ast.Call)
    return (
        isinstance(stmt, ast.Expr)
        and _is_call(stmt.value, "print")
        and len(stmt.value.keywords) == 1
        and ast.dump(stmt.value.keywords[0]) == ast.dump(banner_call.keywords[0])
    )


def _run_stmt(stmt: ast.stmt, mcp_n: str, args_n: str, transport: str) -> bool:
    network = transport != "stdio"
    host = f", host={args_n}.host, port={args_n}.port" if network else ""
    want = _expr_of(f'{mcp_n}.run(transport="{transport}"{host})')
    return isinstance(stmt, ast.Expr) and ast.dump(stmt.value) == ast.dump(want)


def _transport_of(test: ast.expr, args_n: str) -> str | None:
    for t in _TRANSPORTS:
        if ast.dump(test) == ast.dump(_expr_of(f'{args_n}.transport == "{t}"')):
            return t
    return None


def _error_exit(tail: list[ast.stmt]) -> bool:
    """An else branch that reports the bad transport on stderr or the logger and exits non-zero."""
    if not tail:
        return False
    *report, last = tail
    exits = {ast.dump(_expr_of("sys.exit(1)")), ast.dump(ast.parse("raise SystemExit(1)").body[0])}
    if (ast.dump(last.value) if isinstance(last, ast.Expr) else ast.dump(last)) not in exits:
        return False
    for s in report:
        call = _bare_call(s)
        is_log = (
            call is not None
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "logger"
        )
        if not (is_log or _is_stderr_print(s)):
            return False
    return True


def _dispatch(last: ast.stmt, mcp_n: str, args_n: str) -> tuple[str, ...] | None:
    """The transports a hand-written dispatch serves (None = all of the SDK's); _Reject unless it is a plain one."""
    served: list[str] = []
    node: ast.stmt = last
    while True:
        if not isinstance(node, ast.If):
            raise _Reject(f"line {node.lineno}: mcp_server() does not end with a transport dispatch on args.transport")
        t = _transport_of(node.test, args_n)
        if t is None or t in served or len(node.body) != 1 or not _run_stmt(node.body[0], mcp_n, args_n, t):
            raise _Reject(
                f"line {node.lineno}: mcp_server() does not end with the standard transport dispatch "
                "(each branch must be `mcp.run(transport=...)` with host/port from args for network transports)"
            )
        served.append(t)
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            node = node.orelse[0]
            continue
        tail = node.orelse
        break
    if len(tail) == 1 and _run_stmt(tail[0], mcp_n, args_n, "stdio"):
        if "stdio" not in served:
            served.append("stdio")
    elif not _error_exit(tail):
        raise _Reject(f"line {node.lineno}: the transport dispatch does not end in stdio or an error exit")
    got = tuple(t for t in _TRANSPORTS if t in served)
    return None if got == _TRANSPORTS else got


def _analyse_entry(fn: ast.FunctionDef) -> dict[str, Any]:
    body = list(fn.body)
    if body and _doc(body[0]):
        body = body[1:]
    if not body:
        raise _Reject("empty mcp_server()")
    first = body[0]
    if not (
        isinstance(first, ast.Assign)
        and isinstance(first.targets[0], ast.Tuple)
        and _is_call(first.value, "get_mcp_instance")
        and (not first.value.args or ast.dump(first.value.args[0]) == ast.dump(_expr_of("sys.argv[1:]")))
        and len(first.value.args) <= 1
        and not first.value.keywords
    ):
        raise _Reject(f"line {first.lineno}: mcp_server() does not start with get_mcp_instance()")
    names = first.targets[0].elts
    if not (len(names) >= 2 and isinstance(names[0], ast.Name) and isinstance(names[1], ast.Name)):
        raise _Reject(f"line {first.lineno}: mcp_server() does not unpack the server and its arguments")
    mcp_n, args_n = names[0].id, names[1].id
    if _options_dispatch(body, mcp_n, args_n):
        for stmt in body[1:-2]:
            if not _is_stderr_print(stmt):
                raise _Reject(f"line {stmt.lineno}: `{ast.unparse(stmt)[:70]}` is outside the banner/dispatch shape")
        return {"transports": None, "mcp": mcp_n, "args": args_n}
    for stmt in body[1:-1]:
        if not _is_stderr_print(stmt):
            raise _Reject(f"line {stmt.lineno}: `{ast.unparse(stmt)[:70]}` is outside the banner/dispatch shape")
    if len(body) < 2:
        raise _Reject(f"line {first.lineno}: mcp_server() does not end with the standard transport dispatch")
    return {"transports": _dispatch(body[-1], mcp_n, args_n), "mcp": mcp_n, "args": args_n}


def _options_dispatch(body: list[ast.stmt], mcp_n: str, args_n: str) -> bool:
    """``options = {} if stdio else {host, port}`` then ``mcp.run(transport=args.transport, **options)``."""
    if len(body) < 3:
        return False
    assign, run = body[-2], body[-1]
    if not (isinstance(assign, ast.Assign) and len(assign.targets) == 1 and isinstance(assign.targets[0], ast.Name)):
        return False
    opts = assign.targets[0].id
    want = f'{{}} if {args_n}.transport == "stdio" else {{"host": {args_n}.host, "port": {args_n}.port}}'
    return (
        ast.dump(assign.value) == ast.dump(_expr_of(want))
        and isinstance(run, ast.Expr)
        and (ast.dump(run.value) == ast.dump(_expr_of(f"{mcp_n}.run(transport={args_n}.transport, **{opts})")))
    )


def _uses_name(text: str, name: str) -> bool:
    """Whether code (not a comment or docstring prose) names ``name``: an identifier, an alias or a dotted string."""
    tree = _parse(text)
    if tree is None:
        return re.search(rf"\b{name}\b", text) is not None
    dotted = re.compile(rf"(?:[\w]+\.)*{name}")
    for n in ast.walk(tree):
        if (
            (isinstance(n, ast.Name) and n.id == name)
            or (isinstance(n, ast.Attribute) and n.attr == name)
            or (isinstance(n, ast.alias) and name in (n.name.split(".")[-1], n.asname))
            or (isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == name)
            or (isinstance(n, ast.Constant) and isinstance(n.value, str) and dotted.fullmatch(n.value))
        ):
            return True
    return False


def _import_map(tree: ast.Module, pkg: str, own_module: str) -> dict[str, tuple[str, str] | None]:
    """name -> (module, original name) for top-level imports; ``None`` module marks `import x`."""
    out: dict[str, tuple[str, str] | None] = {}
    for n in tree.body:
        if isinstance(n, ast.ImportFrom):
            if n.level > 1:
                continue
            mod = n.module or ""
            if n.level == 1:
                base = own_module.rsplit(".", 1)[0]
                mod = f"{base}.{mod}" if mod else base
            for a in n.names:
                out[a.asname or a.name] = (mod, a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name.split(".")[0]] = (a.name, "")
    return out


def _import_for(name: str, imports: dict, local: set[str], own: str) -> str | None:
    if name in local:
        return f"from {own} import {name}"
    hit = imports.get(name)
    if not hit:
        return None
    mod, orig = hit
    if orig == "":
        return f"import {mod}" if mod == name else f"import {mod} as {name}"
    return f"from {mod} import {orig}" + (f" as {name}" if name != orig else "")


def _runs_mcp_server(body: list[ast.stmt]) -> bool:
    """The body is ``mcp_server()``, alone or under ``if "pytest" not in sys.modules:`` (home-assistant-agent)."""
    if len(body) != 1:
        return False
    only = body[0]
    if isinstance(only, ast.If) and not only.orelse:
        return ast.dump(only.test) == ast.dump(_expr_of('"pytest" not in sys.modules')) and _runs_mcp_server(only.body)
    return isinstance(only, ast.Expr) and _is_call(only.value, "mcp_server")


def _rows_expr(rows: list[tuple[str, str, str]], registrar: Callable[[str, str], None], what: str) -> str:
    """``((tag, toggle, fn), ...)`` source for registry rows; every function is imported through ``registrar``."""
    elts = []
    for tag, toggle, fn in rows:
        registrar(fn, what)
        elts.append(f"({json.dumps(tag)}, {json.dumps(toggle)}, {fn})")
    return "(" + ", ".join(elts) + ",)" if elts else "()"


def _tuple_src(names: list[str]) -> str:
    return "(" + ", ".join(names) + ("," if len(names) == 1 else "") + ")"


_CONTEXT_IMPORT = "from agent_connector_sdk.connector_hooks import RegistrationContext"


def _rewritable(ctx: Ctx, node: ast.FunctionDef, path: Path, kept: list[ast.stmt]) -> bool:
    """A local registration function that nothing else calls may take the RegistrationContext itself."""
    if node.decorator_list or isinstance(node, ast.AsyncFunctionDef):
        return False
    inside = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        a.arg for a in ast.walk(node.args) if isinstance(a, ast.arg)
    }
    if "context" in inside:
        return False
    if any(node.name in _name_loads([n]) for n in kept if n is not node):
        return False
    return not any(_uses_name(f.read_text(encoding="utf-8"), node.name) for f in _py_files(ctx.root) if f != path)


def _extras(
    ctx: Ctx,
    info: dict[str, Any],
    exprs: dict[str, str],
    defs: list[str],
    sig_edits: list[str],
    import_lines: list[str],
    mcp_imports: list[str],
    kept: list[ast.stmt],
    funcs: dict[str, ast.FunctionDef],
    path: Path,
    local: set[str],
    own: str,
) -> None:
    """Express the extra registration calls as ``extra_registrations`` entries that take a RegistrationContext."""
    imports, mcp_n, calls = info["imports"], info["mcp"], info["extras"]

    def simple(c: ast.Call) -> bool:
        return len(c.args) == 1 and not c.keywords and isinstance(c.args[0], ast.Name) and c.args[0].id == mcp_n

    def bring(name: str) -> None:
        line = _import_for(name, imports, local, own)
        if line is None:
            raise _Reject(f"extra registration `{name}` is neither defined nor imported by mcp_server.py")
        import_lines.append(line)

    entries: list[str] = []
    if all(simple(c) for c in calls):
        for c in calls:
            assert isinstance(c.func, ast.Name)
            name = c.func.id
            bring(name)
            target = funcs.get(name)
            if target is not None and _rewritable(ctx, target, path, kept):
                sig_edits.append(name)
                entries.append(name)
                mcp_imports.append(_CONTEXT_IMPORT)
            else:
                adapter = "_register_" + name.removeprefix("register_")
                if adapter in local or adapter in imports:
                    adapter = f"_register_{name}"
                defs.append(f"def {adapter}(context: RegistrationContext) -> None:\n    {name}(context.server)\n")
                import_lines.append(_CONTEXT_IMPORT)
                entries.append(adapter)
    else:
        forbidden = {info["args"], info["mw"], *([info["tags"]] if info["tags"] else [])}
        statements: list[str] = []
        for c in calls:
            params = {a.arg for a in ast.walk(c) if isinstance(a, ast.arg)}
            for name in sorted(_name_loads([c]) - {mcp_n} - params):
                if name in forbidden or name == "context":
                    raise _Reject(f"extra registration `{ast.unparse(c)[:60]}` reads the bootstrap local `{name}`")
                if hasattr(builtins, name) and name not in imports and name not in local:
                    continue
                bring(name)
            statements.append(ast.unparse(_ServerSubst(mcp_n).visit(ast.parse(ast.unparse(c)).body[0])))
        defs.append(
            "def _register_extras(context: RegistrationContext) -> None:\n    " + "\n    ".join(statements) + "\n"
        )
        import_lines.append(_CONTEXT_IMPORT)
        entries.append("_register_extras")
    exprs["extra_registrations"] = _tuple_src(entries)


class _ServerSubst(ast.NodeTransformer):
    """``mcp`` -> ``context.server`` in a registration call moved into an adapter."""

    def __init__(self, name: str) -> None:
        self.name = name

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id == self.name and isinstance(node.ctx, ast.Load):
            return ast.Attribute(value=ast.Name(id="context", ctx=ast.Load()), attr="server", ctx=ast.Load())
        return node


def _context_signature(text: str, name: str) -> tuple[str, set[str]]:
    """Make the one-parameter registration function ``name`` take a RegistrationContext (``mcp = context.server``)."""
    tree = _parse(text)
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None) if tree else None
    if tree is None or fn is None:
        return text, set()
    param = fn.args.args[0]
    lines = text.split("\n")
    body = fn.body
    first = body[0]
    after_doc = _doc(first)
    if after_doc and len(body) > 1:
        at, indent = (first.end_lineno or first.lineno), body[1].col_offset
    elif after_doc:
        at, indent = (first.end_lineno or first.lineno), first.col_offset
    else:
        at, indent = _span(first)[0] - 1, first.col_offset
    lines.insert(at, " " * indent + f"{param.arg} = context.server")
    row = lines[param.lineno - 1].encode("utf-8")
    assert param.end_col_offset is not None and param.lineno == param.end_lineno
    lines[param.lineno - 1] = (
        row[: param.col_offset] + b"context: RegistrationContext" + row[param.end_col_offset :]
    ).decode("utf-8")
    gone = _name_loads([param.annotation]) if param.annotation else set()
    return "\n".join(lines), gone


def _add_sorted_import(text: str, line: str) -> str:
    """Add a top-level ``from m import x`` line next to the imports of the same top-level package, in module order."""
    tree = _parse(text)
    if tree is None or line in text.split("\n"):
        return text
    mod = line.split()[1]
    imps = [n for n in tree.body if isinstance(n, ast.ImportFrom | ast.Import) and getattr(n, "level", 0) == 0]
    if not imps:
        return _add_lines(text, [line])

    def key(n: ast.stmt) -> str:
        return (n.module or "") if isinstance(n, ast.ImportFrom) else n.names[0].name  # type: ignore[attr-defined]

    same = [n for n in imps if key(n).split(".")[0] == mod.split(".")[0]]
    pool = same or imps
    before = [n for n in pool if key(n) <= mod]
    anchor = (before[-1] if before else None) or pool[0]
    if before:
        return _add_lines(text, [line], after=anchor.end_lineno)
    return _add_lines(text, [line], after=anchor.lineno - 1)


def _free_names(f: ast.FunctionDef | ast.AsyncFunctionDef, mcp_n: str) -> set[str]:
    """Names a hoisted function reads that it does not bind itself (its ``mcp.tool`` decorator is not a read)."""
    dec = f.decorator_list[0] if f.decorator_list else None
    parts: list[ast.AST] = [f.args, *f.body]
    if f.returns is not None:
        parts.append(f.returns)
    if isinstance(dec, ast.Call):
        parts += [*dec.args, *[k.value for k in dec.keywords]]
    loads: set[str] = set()
    bound = {f.name}
    for part in parts:
        for n in ast.walk(part):
            if isinstance(n, ast.Name):
                (loads if isinstance(n.ctx, ast.Load) else bound).add(n.id)
            elif isinstance(n, ast.arg):
                bound.add(n.arg)
            elif isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                bound.add(n.name)
            elif isinstance(n, ast.Import | ast.ImportFrom):
                bound |= {_bound(a, n) for a in n.names}
            elif isinstance(n, ast.ExceptHandler) and n.name:
                bound.add(n.name)
    return loads - bound


def _hoist(
    text: str, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """The function's source dedented out of the bootstrap, proven to parse to the identical function."""
    start, end = _span(node)
    block = (
        "\n".join(line[4:] if line.startswith("    ") else line for line in text.split("\n")[start - 1 : end]) + "\n"
    )
    mod = _parse(block)
    if mod is None or len(mod.body) != 1 or not isinstance(mod.body[0], ast.FunctionDef | ast.AsyncFunctionDef):
        raise _Reject(f"`{node.name}` cannot be moved out of the bootstrap")
    if _plain_dump(mod.body[0]) != _plain_dump(node):
        raise _Reject(f"`{node.name}` has a multi-line string that moving it out of the bootstrap would change")
    return block, mod.body[0]


def _plain_dump(node: ast.AST) -> str:
    """``ast.dump`` with every docstring reduced to its dedented text (moving a function re-indents docstrings)."""
    tree = copy.deepcopy(node)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and n.body and _doc(n.body[0]):
            doc = n.body[0]
            assert isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant)
            doc.value.value = inspect.cleandoc(str(doc.value.value))
    return ast.dump(tree)


def _hoisted_function(
    text: str, node: ast.FunctionDef | ast.AsyncFunctionDef, info: dict[str, Any], taken: set[str]
) -> tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    block, f = _hoist(text, node)
    shared = {h.name for h in info["helpers"]}
    clash = _free_names(f, info["mcp"]) & (info["boot_locals"] - shared)
    if clash:
        raise _Reject(f"`{f.name}` reads `{sorted(clash)[0]}` from the bootstrap, which a module-level function cannot")
    if f.name in taken:
        raise _Reject(f"`{f.name}` would replace a module-level name of the same name")
    return block, f


def _hoist_hooks(
    text: str,
    info: dict[str, Any],
    exprs: dict[str, str],
    hoisted: list[str],
    import_lines: list[str],
    mcp_imports: list[str],
    notes: list[str],
    taken: set[str],
    own: str,
) -> None:
    """Inline tools, extra routes and the readiness probe move out of the bootstrap to module level."""
    mcp_n = info["mcp"]
    names: list[str] = []
    if info["helpers"] and not (info["inline"] or info["routes"] or info["ready"] is not None):
        raise _Reject(f"`{info['helpers'][0].name}` is a bootstrap helper that no moved function uses")
    for node in info["helpers"]:
        block, f = _hoisted_function(text, node, info, taken)
        taken.add(f.name)
        hoisted.append(block)
    for node in info["inline"]:
        block, f = _hoisted_function(text, node, info, taken)
        attr = _tool_decorator(f.decorator_list[0], mcp_n)
        replaced = _replace_nodes(block, [attr], "tool") if attr is not None else None
        if replaced is None:
            raise _Reject(f"`{f.name}` has a multi-line @{mcp_n}.tool decorator head")
        if "tool" in taken and info["imports"].get("tool") != ("fastmcp.tools", "tool"):
            raise _Reject("a module-level `tool` already exists, so the hoisted functions cannot use @tool")
        taken.add(f.name)
        mcp_imports.append("from fastmcp.tools import tool")
        hoisted.append(replaced)
        import_lines.append(f"from {own} import {f.name}")
        names.append(f.name)
    if names:
        exprs["inline_tools"] = _tuple_src(names)
    routes: list[str] = []
    for spec in info["routes"]:
        block, f = _hoisted_function(text, spec["node"], info, taken)
        if len(f.args.args) != 1 or f.args.vararg or f.args.kwonlyargs or f.args.kwarg:
            raise _Reject(f"route handler `{f.name}` does not take exactly the request")
        taken.add(f.name)
        hoisted.append("\n".join(block.split("\n")[f.lineno - 1 :]))
        import_lines += [f"from {own} import {f.name}", "from agent_connector_sdk.connector_hooks import Route"]
        methods = (
            "(" + ", ".join(json.dumps(m) for m in spec["methods"]) + ("," if len(spec["methods"]) == 1 else "") + ")"
        )
        routes.append(
            f"Route({json.dumps(spec['path'])}, {f.name}, methods={methods}"
            + (f", name={json.dumps(spec['name'])}" if spec["name"] else "")
            + ")"
        )
    if routes:
        exprs["routes"] = _tuple_src(routes)
    if info["ready"] is not None:
        block, name = _readiness_block(text, info, taken)
        hoisted.append(block)
        mcp_imports.append("from agent_connector_sdk.connector_hooks import Readiness")
        import_lines.append(f"from {own} import {name}")
        exprs["readiness"] = name
        notes.append(
            f"the backend probe served at {info['ready_path']} is now Connector(readiness=...) at /ready and "
            "/health is liveness-only; move the deployment readiness probe to /ready"
        )


def _readiness_block(text: str, info: dict[str, Any], taken: set[str]) -> tuple[str, str]:
    """``async def readiness() -> Readiness`` from a probing handler: a 503 response is not ready, any other is."""
    node = info["ready"]
    block, f = _hoist(text, node)
    if not isinstance(f, ast.AsyncFunctionDef):
        raise _Reject(f"the backend probe `{f.name}` is not an async function")
    clash = _free_names(f, info["mcp"]) & (info["boot_locals"] - {h.name for h in info["helpers"]})
    if clash:
        raise _Reject(f"`{f.name}` reads `{sorted(clash)[0]}` from the bootstrap, which a module-level function cannot")
    a = f.args
    if len(a.args) != 1 or a.vararg or a.kwonlyargs or a.kwarg or a.posonlyargs:
        raise _Reject(f"the backend probe `{f.name}` does not take exactly the request")
    request = a.args[0].arg
    if request in {n.id for stmt in f.body for n in ast.walk(stmt) if isinstance(n, ast.Name)}:
        raise _Reject(f"the backend probe `{f.name}` reads its request")
    name = "readiness"
    if name in taken:
        raise _Reject("a module-level `readiness` already exists")
    taken.add(name)
    caught = {n.name for stmt in f.body for n in ast.walk(stmt) if isinstance(n, ast.ExceptHandler) and n.name}
    edits: list[tuple[int, int, str]] = []
    for stmt in f.body:
        for r in ast.walk(stmt):
            if isinstance(r, ast.Return):
                edits.append((r.lineno, r.end_lineno or r.lineno, _readiness_return(f.name, r, caught)))
    if not edits:
        raise _Reject(f"the backend probe `{f.name}` never returns a response")
    lines = block.split("\n")
    for start, end, new in sorted(edits, reverse=True):
        indent = " " * (lines[start - 1].index(lines[start - 1].lstrip()))
        lines[start - 1 : end] = [indent + part for part in new.split("\n")]
    head_end = (f.returns or a.args[-1]).end_lineno or f.lineno
    first = min([f.lineno, *[d.lineno for d in f.decorator_list]])
    lines[first - 1 : head_end] = [f"async def {name}() -> Readiness:"]
    return "\n".join(lines).rstrip("\n") + "\n", name


def _readiness_return(fn: str, r: ast.Return, caught: set[str]) -> str:
    """``return JSONResponse({...}, status_code=503)`` -> ``return Readiness(False, {...})`` without exception text."""
    call = r.value
    if not (
        isinstance(call, ast.Call)
        and _is_call(call, "JSONResponse")
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Dict)
        and all(k.arg == "status_code" for k in call.keywords)
        and len(call.keywords) <= 1
    ):
        raise _Reject(f"the backend probe `{fn}` returns something other than JSONResponse({{...}}[, status_code=...])")
    status = 200
    if call.keywords:
        code = call.keywords[0].value
        if not (isinstance(code, ast.Constant) and code.value in (200, 503)):
            raise _Reject(f"the backend probe `{fn}` returns a status other than 200 or 503")
        status = 200 if code.value == 200 else 503
    payload = call.args[0]
    detail: dict[str, ast.expr] = {}
    for k, v in zip(payload.keys, payload.values, strict=True):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
            raise _Reject(f"the backend probe `{fn}` returns a payload with a computed key")
        if k.value == "status" or _name_loads([v]) & caught:
            continue  # the SDK sets the status; an exception's text is never served
        detail[k.value] = v
    items = ", ".join(f"{json.dumps(k)}: {_src(v)}" for k, v in detail.items())
    return f"return Readiness({status != 503}{', {' + items + '}' if detail else ''})"


def _drop_action_module(ctx: Ctx, module: str, rel: str) -> None:
    """The package's own action-split module goes when nothing imports it any more."""
    f = _module_file(ctx, module)
    if f is None or f.name == "__init__.py":
        return
    users = [
        ctx.rel(o) for o in _py_files(ctx.root) if o != f and re.search(rf"\b{f.stem}\b", o.read_text(encoding="utf-8"))
    ]
    if users:
        ctx.note("w1.g3", f"{ctx.rel(f)} stays: {users[0]} still names {f.stem}, the SDK serves action tools now", rel)
        return
    ctx.delete(ctx.rel(f), "w1.g3")
    ctx.note("w1.g3", f"deleted {ctx.rel(f)}: the SDK's Connector(action_tools=...) serves one tool per action", rel)


@rule("w1.g3")
def g3(ctx: Ctx) -> None:
    path = ctx.pkg / "mcp_server.py"
    if path.is_file():
        _g3_run(ctx, path, f"{ctx.pkg_name}.mcp_server", None)


def _export_registrars(text: str) -> str:
    """List imported ``register_<tag>_tools`` names that nothing else references in ``__all__``."""
    tree = _parse(text)
    if tree is None:
        return text
    imported = [
        _bound(a, n)
        for n in tree.body
        if isinstance(n, ast.Import | ast.ImportFrom) and getattr(n, "module", "") != "__future__"
        for a in n.names
    ]
    used = _referenced(tree)
    missing = sorted({n for n in imported if _REGISTRAR.fullmatch(n) and n not in used})
    if not missing:
        return text
    listed = ", ".join(json.dumps(n) for n in missing)
    for n in tree.body:
        if (
            isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)
            and isinstance(n.value, ast.List | ast.Tuple)
        ):
            value = n.value
            if value.elts:
                last = value.elts[-1]
                assert last.end_lineno is not None and last.end_col_offset is not None
                rows = text.split("\n")
                row = rows[last.end_lineno - 1].encode("utf-8")
                rows[last.end_lineno - 1] = (
                    row[: last.end_col_offset] + f", {listed}".encode() + row[last.end_col_offset :]
                ).decode("utf-8")
                return "\n".join(rows)
            replaced = _replace_nodes(text, [value], f"[{listed}]")
            return replaced if replaced is not None else text
    note = "# SDK discovery registers the register_<tag>_tools functions bound in this module."
    return _add_lines(text, ["", note, f"__all__ = [{listed}]"])


def _is_build_wrapper(n: ast.stmt) -> bool:
    """``def build_server(*, command_args=None): return get_mcp_instance(command_args=command_args)[0]``."""
    if not (isinstance(n, ast.FunctionDef) and n.name == "build_server"):
        return False
    a = n.args
    if a.args or a.posonlyargs or a.vararg or a.kwarg or [k.arg for k in a.kwonlyargs] != ["command_args"]:
        return False
    body = [x for x in n.body if not _doc(x)]
    want = ast.dump(_expr_of("get_mcp_instance(command_args=command_args)[0]"))
    return len(body) == 1 and isinstance(body[0], ast.Return) and ast.dump(body[0].value) == want  # type: ignore[arg-type]


def _delegate_build_server(text: str, pkg: str) -> str:
    """The wrapper answers with the SDK's ``build_server``: its ``(args, mcp)`` result, mcp second."""
    tree = _parse(text)
    fn = (
        next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_server"), None)
        if tree
        else None
    )
    if fn is None:
        return text
    ret = next(x for x in fn.body if isinstance(x, ast.Return))
    indent = " " * ret.col_offset
    call = f'return _sdk_build_server("{pkg}", command_args=command_args)[1]'
    return _replace_span(text, ret.lineno, ret.end_lineno or ret.lineno, indent + call)


def _in_all(text: str) -> bool:
    """Whether a literal ``__all__`` lists ``get_mcp_instance``: the module re-exports it rather than using it."""
    tree = _parse(text)
    return tree is not None and any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)
        and any(isinstance(e, ast.Constant) and e.value == "get_mcp_instance" for e in ast.walk(n.value))
        for n in tree.body
    )


def _strip_reexport(text: str) -> str | None:
    """The thin wrapper without ``get_mcp_instance`` / ``mcp_server`` (import and ``__all__``), else None."""
    tree = _parse(text)
    if tree is None:
        return None
    gone = {"get_mcp_instance", "mcp_server"}
    spans: list[tuple[int, int]] = []
    edits: list[tuple[int, int, str]] = []
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and any(a.name in gone for a in n.names):
            keep = [a for a in n.names if a.name not in gone]
            if keep:
                edits.append((n.lineno, n.end_lineno or n.lineno, _import_text(n, keep)))
            else:
                spans.append((n.lineno, n.end_lineno or n.lineno))
        elif (
            isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)
            and isinstance(n.value, ast.List | ast.Tuple)
        ):
            lines = text.split("\n")
            if all(isinstance(e, ast.Constant) and e.value in gone for e in n.value.elts):
                spans.append((n.lineno, n.end_lineno or n.lineno))
                continue
            for e in n.value.elts:
                if isinstance(e, ast.Constant) and e.value in gone:
                    if e.lineno != e.end_lineno or lines[e.lineno - 1].strip() not in (
                        f'"{e.value}",',
                        f"'{e.value}',",
                    ):
                        return None
                    spans.append((e.lineno, e.lineno))
    if not spans and not edits:
        return None
    for start, end, new in sorted([*edits, *[(a, b, "") for a, b in spans]], reverse=True):
        text = _replace_span(text, start, end, new) if new else _delete_spans(text, [(start, end)])
    return text


def _g3_second_module(ctx: Ctx, dotted: str, wrapper: Path) -> None:
    """``mcp_server.py`` only re-exports the bootstrap of another module of the package: extract from that module."""
    real = _module_file(ctx, dotted)
    if real is None or real == wrapper or ctx.pkg not in real.parents:
        ctx.note(
            "w1.g3",
            f"mcp_server.py only re-exports get_mcp_instance from {dotted}, which is not a module of this package",
            ctx.rel(wrapper),
            blocking=True,
        )
        return
    _g3_run(ctx, real, dotted, wrapper)


_PURE_CALLS = frozenset({"getattr", "dict", "list", "tuple", "set", "frozenset", "len", "str", "int", "bool", "sorted"})
_PURE_METHODS = frozenset({"items", "keys", "values", "append", "extend", "get", "copy"})


def _check_targets_timing(node: ast.expr, kept: Sequence[ast.stmt]) -> None:
    """``verbose_targets=f()`` ran while the server was built, after ``load_config()``; ``Connector`` evaluates it at import.

    Only a call to a local function that reads nothing at call time (no calls outside a lambda but pure builtins, no
    ``environ``) moves exactly. Any other call may read the configuration (a deployment switch) and is refused: the SDK
    has no lazy form of ``verbose_targets`` (an SDK gap, not a rewrite the codemod can make exact).
    """
    if not isinstance(node, ast.Call):
        return
    func = next(
        (
            n
            for n in kept
            if isinstance(n, ast.FunctionDef) and isinstance(node.func, ast.Name) and n.name == node.func.id
        ),
        None,
    )
    reason = "calls a function this module does not define"
    if func is not None and not node.args and not node.keywords:
        reason = ""

        def walk(n: ast.AST) -> None:
            nonlocal reason
            if isinstance(n, ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and n is not func:
                return
            pure = isinstance(n, ast.Call) and (
                (isinstance(n.func, ast.Name) and n.func.id in _PURE_CALLS)
                or (isinstance(n.func, ast.Attribute) and n.func.attr in _PURE_METHODS)
            )
            if isinstance(n, ast.Call) and not pure and not reason:
                reason = f"`{ast.unparse(n.func)}(...)` runs inside it"
            elif isinstance(n, ast.Attribute) and n.attr in ("environ", "getenv") and not reason:
                reason = "it reads the environment"
            for child in ast.iter_child_nodes(n):
                walk(child)

        walk(func)
    elif func is not None:
        reason = "it takes arguments"
    if reason:
        raise _Reject(
            f"verbose_targets={ast.unparse(node)} is evaluated when the server is built (after load_config()) but "
            f"Connector(verbose_targets=...) is evaluated at import ({reason}); SDK gap: no lazy verbose_targets"
        )


def _g3_run(ctx: Ctx, path: Path, modname: str, wrapper: Path | None) -> None:
    rel = ctx.rel(path)
    text = path.read_text(encoding="utf-8")
    tree = _parse(text)
    if tree is None:
        ctx.note("w1.g3", "mcp_server.py does not parse", rel, blocking=True)
        return
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    if "get_mcp_instance" not in funcs:
        if "mcp_server" in funcs:
            ctx.note(
                "w1.g3",
                "mcp_server() exists without get_mcp_instance(); the server is composed by a separate build_server() "
                "that shares state such as a clients holder between registrars. SDK 0.5.3 expresses that as a "
                "`register_tools(context: RegistrationContext)` extra registration, which the codemod does not "
                "write yet: hand-write it",
                rel,
                blocking=True,
            )
        else:
            moved = [
                f"{n.module}"
                for n in tree.body
                if isinstance(n, ast.ImportFrom)
                and n.level == 0
                and n.module
                and any(a.name == "get_mcp_instance" for a in n.names)
            ]
            if moved and wrapper is None:
                _g3_second_module(ctx, moved[0], path)
            elif moved:
                ctx.note("w1.g3", f"{rel} re-exports get_mcp_instance again from {moved[0]}", rel, blocking=True)
        return
    env = _Env(ctx, tree, _import_map(tree, ctx.pkg_name, modname), modname)
    entry: dict[str, Any] = {"transports": None}
    try:
        info = _analyse_instance(funcs["get_mcp_instance"], funcs, env)
        if "mcp_server" in funcs:
            entry = _analyse_entry(funcs["mcp_server"])
            if info["ret"][:2] != [info["mcp"], info["args"]]:
                raise _Reject("get_mcp_instance() does not return the server and its arguments first")
    except _Reject as err:
        ctx.note(
            "w1.g3", f"get_mcp_instance/mcp_server is not the plain bootstrap, hand-write Connector: {err}", rel, True
        )
        return
    # nodes to delete
    dele: list[ast.stmt] = [funcs["get_mcp_instance"]]
    if "mcp_server" in funcs:
        dele.append(funcs["mcp_server"])
    main_if = [
        n
        for n in tree.body
        if isinstance(n, ast.If)
        and ast.dump(n.test) == ast.dump(_expr_of('__name__ == "__main__"'))
        and not n.orelse
        and _runs_mcp_server(n.body)
    ]
    dele += main_if
    kept = [n for n in tree.body if n not in dele]
    logger_nodes = [
        n
        for n in tree.body
        if (
            isinstance(n, ast.Assign)
            and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id == "logger"
            and isinstance(n.value, ast.Call)
            and ast.unparse(n.value.func).endswith("get_logger")
        )
        or (
            isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and ast.unparse(n.value.func) == "logger.setLevel"
        )
    ]
    ver_nodes = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign | ast.AnnAssign)
        and ast.unparse(n.targets[0] if isinstance(n, ast.Assign) else n.target) == "__version__"
        and isinstance(n.value, ast.Constant)
        and isinstance(n.value.value, str)
    ]
    stderr_kw = _expr_of('print("x", file=sys.stderr)')
    assert isinstance(stderr_kw, ast.Call)
    banner_nodes = [
        n
        for n in kept
        if isinstance(n, ast.Expr)
        and _is_call(n.value, "print")
        and len(n.value.keywords) == 1
        and ast.dump(n.value.keywords[0]) == ast.dump(stderr_kw.keywords[0])
        and "__version__" in _name_loads([n])
        and _name_loads([n]) <= {"print", "sys", "__version__"}
    ]
    rest = [n for n in kept if n not in logger_nodes and n not in ver_nodes and n not in banner_nodes]
    if logger_nodes and "logger" not in _name_loads(n for n in rest if n not in logger_nodes):
        dele += logger_nodes
    if ver_nodes and "__version__" not in _name_loads(rest + [n for n in logger_nodes if n not in dele]):
        dele += ver_nodes
        dele += banner_nodes
    tags = info["tags"]
    if tags and tags in _name_loads(n for n in kept):
        ctx.note("w1.g3", f"`{tags}` (the registered tags) is used outside the bootstrap; hand-migrate", rel, True)
        return
    # the rest of mcp_server.py must not call the deleted functions
    gone = {"get_mcp_instance", "mcp_server"}
    wrappers = [n for n in kept if _is_build_wrapper(n)]
    for n in kept:
        if n not in dele and n not in wrappers and (gone & _name_loads([n])):
            ctx.note(
                "w1.g3",
                f"line {n.lineno}: mcp_server.py itself still uses {sorted(gone & _name_loads([n]))[0]} outside the "
                "bootstrap (a wrapper such as build_server); hand-migrate it and its importers",
                rel,
                True,
            )
            return
    # other modules must not import the deleted functions
    reexports: dict[Path, str] = {}
    for other in _py_files(ctx.pkg):
        if other in (path, wrapper) or other.name == "__main__.py" and other.parent == ctx.pkg:
            continue
        other_text = other.read_text(encoding="utf-8")
        if _uses_name(other_text, "get_mcp_instance"):
            stripped = _strip_reexport(other_text)
            if stripped is None or _uses_name(stripped, "get_mcp_instance") or not _in_all(other_text):
                ctx.note("w1.g3", "another module uses get_mcp_instance; hand-migrate", ctx.rel(other), True)
                return
            reexports[other] = stripped
    # extraction
    imports = info["imports"]
    local = _top_defs(ast.Module(body=kept, type_ignores=[]))
    own = modname
    import_lines: list[str] = []
    exprs: dict[str, str] = {}
    defs: list[str] = []
    notes: list[str] = []
    hoisted: list[str] = []
    sig_edits: list[str] = []
    mcp_imports: list[str] = []
    prune_extra: set[str] = set()

    def need(node: ast.expr, what: str) -> None:
        for name in sorted(_name_loads([node])):
            if hasattr(builtins, name) and name not in imports and name not in local:
                continue
            line = _import_for(name, imports, local, own)
            if line is None:
                raise _Reject(f"{what} uses `{name}` which mcp_server.py does not define or import")
            import_lines.append(line)

    def registrar(fn_name: str, what: str) -> None:
        line = _import_for(fn_name, imports, local, own)
        if line is None:
            raise _Reject(f"{what} `{fn_name}` is neither defined nor imported by mcp_server.py")
        import_lines.append(line)

    try:
        ins = info["instructions"]
        if isinstance(ins, ast.Constant) and isinstance(ins.value, str):
            exprs["instructions"] = _src(ins)
        elif isinstance(ins, ast.Name) and ins.id in local:
            exprs["instructions"] = ins.id
            need(ins, "instructions")
        else:
            raise _Reject("instructions= is neither a string literal nor a module constant")
        surf = info["surface"]
        if "client_cls" in surf:
            need(surf["client_cls"], "client_cls")
            need(surf["get_client"], "get_client")
        if "manifest" in surf:
            need(surf["manifest"], "manifest")
            main = ast.Dict(
                keys=[ast.Constant("client_cls"), ast.Constant("get_client"), ast.Constant("manifest")],
                values=[surf["client_cls"], surf["get_client"], surf["manifest"]],
            )
            given = surf.get("verbose_targets")
            more: list[ast.expr] = (
                []
                if given is None
                else list(given.elts)
                if isinstance(given, ast.List)
                else [ast.Starred(given, ast.Load())]
            )
            exprs["verbose_targets"] = ast.unparse(ast.Tuple(elts=[main, *more], ctx=ast.Load()))
            if given is not None:
                _check_targets_timing(given, kept)
                need(given, "verbose_targets")
        elif "client_cls" in surf:
            exprs["api"] = surf["client_cls"].id
            exprs["get_client"] = surf["get_client"].id
        for key in _SURFACE_KWARGS:
            if key not in surf or (key == "verbose_targets" and "manifest" in surf):
                continue
            node = surf[key]
            if key == "verbose_targets":
                node = ast.Tuple(elts=node.elts, ctx=ast.Load()) if isinstance(node, ast.List) else None
                exprs[key] = ast.unparse(node) if node else f"tuple({ast.unparse(surf[key])})"
                _check_targets_timing(surf[key], kept)
                need(surf[key], key)
            else:
                exprs[key] = _src(node)
                need(node, key)
        reg = info.get("registry")
        if reg and "rows" in reg:
            exprs["tool_registry"] = _rows_expr(reg["rows"], registrar, "registrar")
        elif reg:
            registrar(reg["name"], "tool registry")
            exprs["tool_registry"] = f"tuple({reg['name']})"
        if info["actions"]:
            rows = [r for a in info["actions"] for r in a["rows"]]
            prefixes: dict[str, str] = {}
            for a in info["actions"]:
                if set(prefixes) & set(a["prefixes"]):
                    raise _Reject("two action registrations name the same tool prefix")
                prefixes.update(a["prefixes"])
            exprs["action_tools"] = _rows_expr(rows, registrar, "action registrar")
            if prefixes:
                exprs["action_prefixes"] = (
                    "{" + ", ".join(f"{json.dumps(k)}: {json.dumps(v)}" for k, v in prefixes.items()) + "}"
                )
        if info["extras"]:
            _extras(ctx, info, exprs, defs, sig_edits, import_lines, mcp_imports, kept, funcs, path, local, own)
        if info["inline"] or info["routes"] or info["ready"] is not None or info["helpers"]:
            _hoist_hooks(
                text,
                info,
                exprs,
                hoisted,
                import_lines,
                mcp_imports,
                notes,
                set(local) | set(imports),
                own,
            )
        if info["tools"] is None and "tool_registry" not in exprs and _module_file(ctx, f"{ctx.pkg_name}.tools"):
            raise _Reject(f"no tools_module is passed, but {ctx.pkg_name}.tools exists and the SDK loads it by default")
        if info["tools"]:
            exprs["tools"] = info["tools"]
        if entry["transports"]:
            exprs["transports"] = "(" + ", ".join(json.dumps(t) for t in entry["transports"]) + ",)"
        if info["content_root"]:
            exprs["content_root"] = json.dumps(info["content_root"])
    except _Reject as err:
        ctx.note("w1.g3", f"cannot extract Connector values: {err}", rel, True)
        return
    # the surface expressions may name things this rule deletes
    deleted_names = {n.name for n in dele if isinstance(n, ast.FunctionDef)}
    if any(f"from {own} import {n}" in import_lines for n in deleted_names):
        ctx.note("w1.g3", "a Connector value names a function the bootstrap deletes", rel, True)
        return
    candidates = _name_loads(dele) - set(info["keep"])
    new = _delete_spans(text, [_span(n) for n in dele])
    for block in hoisted:
        new = new.rstrip("\n") + "\n\n\n" + block
    for name in sig_edits:
        new, gone = _context_signature(new, name)
        prune_extra |= gone
    if wrappers:
        new = _delegate_build_server(new, ctx.pkg_name)
        mcp_imports.append("from agent_connector_sdk.connector import build_server as _sdk_build_server")
    for line in dict.fromkeys(mcp_imports):
        new = _add_sorted_import(new, line)
    new = _prune_imports(new, candidates | prune_extra)
    if info["tools"] == modname:
        new = _export_registrars(new)  # SDK discovery reads this namespace; the unused-import tidy must keep it
    if wrapper is not None:
        stripped = _strip_reexport(wrapper.read_text(encoding="utf-8"))
        if stripped is None:
            ctx.note("w1.g3", f"cannot remove the re-export of the bootstrap from {ctx.rel(wrapper)}", rel, True)
            return
        reexports[wrapper] = stripped
    for other, other_text in reexports.items():
        ctx.write(ctx.rel(other), other_text, "w1.g3")
    ctx.write(rel, new, "w1.g3")
    ctx.options[_G3_KEY] = {
        "exprs": exprs,
        "imports": sorted(set(import_lines), key=lambda s: (s.startswith("from agent"), s)),
        "health": info["health"],
        "module": modname,
        "defs": defs,
    }
    for module in sorted({a["module"] for a in info["actions"]}):
        _drop_action_module(ctx, module, rel)
    for note in notes:
        ctx.note("w1.g3", note, rel)
    if info["content_name"]:
        ctx.note(
            "w1.g3",
            f"content was filed under the connector name {info['content_name']!r}; the SDK files it under the fleet "
            f"name {ctx.fleet!r}, review the content pack name",
            rel,
        )
    if entry["transports"]:
        ctx.note(
            "w1.g3",
            "mcp_server() served only " + ", ".join(entry["transports"]) + "; declared as Connector(transports=...)",
            rel,
        )
    if info.get("ordered"):
        ctx.note(
            "w1.g3",
            "registrar tools register in the SDK's sorted register_<tag>_tools order instead of the listed order",
            rel,
        )
    if info["inert"]:
        ctx.note(
            "w1.g3",
            "dropped the `--openapi-file` import block; the SDK parser defines no such flag, so it never ran",
            rel,
        )
    if info["env"]:
        ctx.note(
            "w1.g3",
            "dropped os.environ lines for " + ", ".join(info["env"]) + "; the SDK server does not set them",
            rel,
        )
    if banner_nodes and banner_nodes[0] in dele:
        ctx.note("w1.g3", "deleted the module-level stderr version banner; the SDK serves the version", rel)
    if info["health"]:
        ctx.applied.append("w1.g6") if "w1.g6" not in ctx.applied else None


# --- g.4 package __init__ ---------------------------------------------------------------------------------
_SCAFFOLD_NAMES = {
    "CORE_MODULES",
    "OPTIONAL_MODULES",
    "_expose_members",
    "_import_module_safely",
    "__getattr__",
    "__all__",
    "_loaded_optional_modules",
    "_AVAILABILITY_FLAGS",
    "_optional_module_is_available",
    "_load_optional_module",
    "_resolve_from_optional_modules",
    "__dir__",
    "__version__",
}
_SCAFFOLD_REQUIRED = {
    "CORE_MODULES",
    "OPTIONAL_MODULES",
    "_expose_members",
    "_import_module_safely",
    "__getattr__",
    "__all__",
}


def _scaffold(tree: ast.Module) -> dict[str, Any] | None:
    """Return the CORE/OPTIONAL module tables when the whole body is the lazy-import scaffold."""
    seen: set[str] = set()
    core: list[str] = []
    optional: list[str] = []
    for n in tree.body:
        if _doc(n):
            continue
        if isinstance(n, ast.Import | ast.ImportFrom):
            mod = n.module if isinstance(n, ast.ImportFrom) else None
            names = {a.name for a in n.names} if isinstance(n, ast.Import) else {mod}
            if names - {"importlib", "inspect", "typing", "__future__"}:
                return None
            continue
        if isinstance(n, ast.FunctionDef):
            if n.name not in _SCAFFOLD_NAMES:
                return None
            seen.add(n.name)
            continue
        if isinstance(n, ast.Assign | ast.AnnAssign):
            target = n.targets[0] if isinstance(n, ast.Assign) else n.target
            if not isinstance(target, ast.Name) or target.id not in _SCAFFOLD_NAMES or n.value is None:
                return None
            seen.add(target.id)
            try:
                if target.id == "CORE_MODULES":
                    core = list(ast.literal_eval(n.value))
                elif target.id == "OPTIONAL_MODULES":
                    optional = list(ast.literal_eval(n.value))
                elif target.id == "__all__" and ast.literal_eval(n.value) != []:
                    return None
            except (ValueError, TypeError):
                return None
            continue
        if isinstance(n, ast.For) and isinstance(n.iter, ast.Name) and n.iter.id == "CORE_MODULES":
            continue
        return None
    if not _SCAFFOLD_REQUIRED <= seen:
        return None
    return {"core": core, "optional": optional}


def _scaffold_edit(ctx: Ctx) -> tuple[str, dict[str, str]] | None:
    """The scaffold-free ``__init__`` head and the import rewrites for ``from <pkg> import X`` users, or None."""
    init = ctx.pkg / "__init__.py"
    if not init.is_file():
        return None
    text = init.read_text(encoding="utf-8")
    tree = _parse(text)
    if tree is None:
        return None
    sc = _scaffold(tree)
    if sc is None:
        return None
    head = ""
    if tree.body and _doc(tree.body[0]):
        head = "\n".join(text.split("\n")[: tree.body[0].end_lineno]) + "\n"
    else:
        lead = []
        for line in text.split("\n"):
            if line.startswith("#"):
                lead.append(line)
            else:
                break
        head = "\n".join(lead) + "\n" if lead else ""
    owner: dict[str, str] = {}
    for mod in [*sc["core"], *sc["optional"]]:
        f = ctx.root / (mod.replace(".", "/") + ".py")
        t = _parse(f.read_text(encoding="utf-8")) if f.is_file() else None
        for name in _top_defs(t) if t else ():
            if not name.startswith("_"):
                owner.setdefault(name, mod)
    return head, owner


def _rewrite_pkg_imports(ctx: Ctx, owner: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Rewrites of ``from <pkg> import X`` to ``from <pkg>.<mod> import X``; (path -> new text, unresolved)."""
    edits: dict[str, str] = {}
    bad: list[str] = []
    for f in _py_files(ctx.root):
        if f == ctx.pkg / "__init__.py":
            continue
        text = f.read_text(encoding="utf-8")
        if not re.search(rf"\b{ctx.pkg_name}\b", text) and not _relative_init_import(ctx, f):
            continue
        tree = _parse(text)
        if tree is None:
            continue
        original = text
        text, tree = _drop_scaffold_tests(ctx, f, text, tree, bad)
        if ctx.rel(f) in ctx.options.get(_G4_FILES, ()):
            continue
        rep: list[tuple[int, int, str]] = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.ImportFrom) or not _targets_pkg_init(ctx, f, n):
                continue
            groups: dict[str, list[ast.alias]] = {}
            for a in n.names:
                if a.name in ("connector", "*") or (ctx.pkg / f"{a.name}.py").is_file() or (ctx.pkg / a.name).is_dir():
                    groups.setdefault("", []).append(a)
                elif a.name in owner:
                    groups.setdefault(owner[a.name], []).append(a)
                else:
                    bad.append(f"{ctx.rel(f)}: {a.name}")
            if set(groups) <= {""}:
                continue
            lines = []
            for mod, aliases in groups.items():
                new_imp = ast.ImportFrom(module=mod or ctx.pkg_name, names=aliases, level=0)
                lines.append(_import_text(new_imp, aliases))
            rep.append((n.lineno, n.end_lineno or n.lineno, "\n".join(lines)))
        for start, end, new in sorted(rep, reverse=True):
            text = _replace_span(text, start, end, new)
        if rep or text != original:
            edits[ctx.rel(f)] = text
    return edits, bad


_SCAFFOLD_TEST_NAMES = _SCAFFOLD_NAMES - {"__version__"}
_SCAFFOLD_ATTR = re.compile(
    r"_[A-Z][A-Z_]*_AVAILABLE|_AVAILABILITY_FLAGS|CORE_MODULES|OPTIONAL_MODULES|_expose_members|_import_module_safely"
    r"|_loaded_optional_modules|_resolve_from_optional_modules|_load_optional_module|_optional_module_is_available"
)


def _enclosing_test(tree: ast.Module, line: int) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for n in tree.body:
        scope = n.body if isinstance(n, ast.ClassDef) else [n]
        for m in scope:
            if (
                isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
                and m.name.startswith("test")
                and m.lineno <= line <= (m.end_lineno or m.lineno)
            ):
                return m
    return None


def _dunder_arg(call: ast.Call) -> bool:
    """``hasattr(m, "__version__")``-style reads of a module dunder, which the scaffold does not provide."""
    arg = call.args[1] if len(call.args) > 1 else None
    return (
        isinstance(arg, ast.Constant)
        and isinstance(arg.value, str)
        and arg.value.startswith("__")
        and arg.value.endswith("__")
    )


def _scaffold_reader(ctx: Ctx, tree: ast.Module, within: ast.AST | None = None) -> str | None:
    """What, if anything, still reads the package through the lazy-import scaffold (module attributes, dir()).

    ``within`` limits the search to one subtree (a test function); the package aliases come from the whole module.
    """
    aliases = {
        a.asname or a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.Import)
        for a in n.names
        if a.name == ctx.pkg_name
    }
    for n in ast.walk(within if within is not None else tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in aliases:
            if _SCAFFOLD_ATTR.fullmatch(n.attr):
                return f"{n.value.id}.{n.attr}"
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in ("dir", "hasattr", "getattr", "vars")
            and n.args
            and isinstance(n.args[0], ast.Name)
            and n.args[0].id in aliases
            and not _dunder_arg(n)
        ):
            return f"{n.func.id}({n.args[0].id})"
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith(ctx.pkg_name + "."):
            if _SCAFFOLD_ATTR.fullmatch(n.value.rsplit(".", 1)[-1]):
                return n.value
    return None


def _drop_scaffold_tests(ctx: Ctx, f: Path, text: str, tree: ast.Module, bad: list[str]) -> tuple[str, ast.Module]:
    """Delete the test functions that exercise the scaffold itself; keep the file when anything else reads it.

    A test exercises the scaffold when it imports one of its helpers or reads the package through it (a lazily
    exposed attribute, ``dir``/``hasattr``/``getattr`` of the package, a scaffold table). When that leaves the file
    without a test, the file goes whole (its path is recorded under ``_G4_FILES``).
    """
    hits = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        and _targets_pkg_init(ctx, f, n)
        and any(a.name in _SCAFFOLD_TEST_NAMES for a in n.names)
    ]
    doomed: dict[int, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for n in hits:
        fn = _enclosing_test(tree, n.lineno)
        if fn is None:
            bad.append(f"{ctx.rel(f)}: {', '.join(a.name for a in n.names)} (imported outside a test function)")
            return text, tree
        doomed[fn.lineno] = fn
    for _name, fn, _cls in _test_nodes(tree):
        if _scaffold_reader(ctx, tree, fn) is not None:
            doomed[fn.lineno] = fn
    if not doomed:
        return text, tree
    new = _delete_spans(text, [_span(fn) for fn in doomed.values()])
    new = _prune_imports(new, _name_loads(doomed.values()))
    new_tree = _parse(new)
    if new_tree is None:
        return text, tree
    reader = _scaffold_reader(ctx, new_tree)
    if reader is not None:
        bad.append(f"{ctx.rel(f)}: {reader} (read outside a test function or by a test that is not scaffold-only)")
        return text, tree
    names = ", ".join(sorted(fn.name for fn in doomed.values()))
    ctx.options.setdefault(_G4_NOTES, []).append(
        (ctx.rel(f), f"deleted test(s) {names}: they exercise the removed lazy-import scaffold itself")
    )
    if not _test_nodes(new_tree) and _test_nodes(tree):
        stem = f.stem
        users = [
            ctx.rel(o)
            for o in _py_files(ctx.root)
            if o != f and re.search(rf"\b(?:from|import)\s+(?:[\w.]*\.)?{re.escape(stem)}\b", o.read_text("utf-8"))
        ]
        if users:
            bad.append(f"{ctx.rel(f)}: every test exercises the scaffold, but {users[0]} imports the file")
            return text, tree
        ctx.options.setdefault(_G4_FILES, []).append(ctx.rel(f))
    return new, new_tree


def _relative_init_import(ctx: Ctx, f: Path) -> bool:
    return f.parent == ctx.pkg and bool(re.search(r"^from \. import ", f.read_text(encoding="utf-8"), re.M))


def _targets_pkg_init(ctx: Ctx, f: Path, n: ast.ImportFrom) -> bool:
    if n.level == 0:
        return n.module == ctx.pkg_name
    return n.level == 1 and n.module is None and f.parent == ctx.pkg


def _remove_scaffold(ctx: Ctx, rule_id: str) -> str | None:
    """Delete the scaffold from ``__init__`` (when it is exactly the scaffold); returns the new head or None."""
    edit = _scaffold_edit(ctx)
    if edit is None:
        return None
    head, owner = edit
    edits, bad = _rewrite_pkg_imports(ctx, owner)
    if bad:
        ctx.options.pop(_G4_NOTES, None)
        ctx.options.pop(_G4_FILES, None)
        ctx.note(
            rule_id,
            f"lazy-import scaffold kept: names with no core module owner or tests that still exercise it: {bad}",
            ctx.rel(ctx.pkg / "__init__.py"),
            True,
        )
        return None
    for rel, new in edits.items():
        ctx.write(rel, new, rule_id)
    for rel in ctx.options.pop(_G4_FILES, []):
        ctx.delete(rel, rule_id)
    for rel, why in ctx.options.pop(_G4_NOTES, []):
        ctx.note(rule_id, why, rel)
    _delete_scaffold_tests(ctx)
    return head


@rule("w1.g4")
def g4(ctx: Ctx) -> None:
    init = ctx.pkg / "__init__.py"
    rel = ctx.rel(init)
    stash = ctx.options.get(_G3_KEY)
    if _declared(ctx):
        return
    if stash is None:
        mcp = ctx.pkg / "mcp_server.py"
        if mcp.is_file() and "def get_mcp_instance" in mcp.read_text(encoding="utf-8"):
            return  # g3 reviewed it
        if any(i["step"] == "w1.g3" and i["blocking"] for i in ctx.review.items):
            return  # g3 already said why there is nothing to extract
        ctx.note(
            "w1.g4", "no `connector = Connector(...)` in the package and no bootstrap to extract it from", rel, True
        )
        return
    text = init.read_text(encoding="utf-8") if init.is_file() else ""
    head = _remove_scaffold(ctx, "w1.g4")
    base = head if head is not None else text
    exprs = stash["exprs"]
    sdk = "from agent_connector_sdk.connector import Connector"
    lines = [sdk, "", *stash["imports"]]
    kw = []
    if "api" in exprs:
        kw += [f"    api={exprs['api']},", f"    get_client={exprs['get_client']},"]
    if "tools" in exprs:
        kw.append(f'    tools="{exprs["tools"]}",')
    if "tool_registry" in exprs:
        kw.append(f"    tool_registry={exprs['tool_registry']},")
    kw.append(f"    instructions={exprs['instructions']},")
    kw += [f"    {k}={exprs[k]}," for k in ("transports", *_SURFACE_KWARGS, *_HOOK_KWARGS) if k in exprs]
    defs = stash.get("defs") or []
    if defs:
        head_block = "\n".join([*lines, ""]) + "\n\n" + "\n\n".join(d.rstrip("\n") + "\n" for d in defs)
        block = head_block + "\n\nconnector = Connector(\n" + "\n".join(kw) + "\n)\n"
    else:
        block = "\n".join([*lines, "", "connector = Connector(", *kw, ")"]) + "\n"
    out = (base.rstrip() + "\n\n" if base.strip() else "") + block
    if _tests_read_all(ctx):
        out += '\n__all__ = ["connector"]\n'  # `assert hasattr(module, "__all__")` of the scaffolded init test
    ctx.write(rel, out, "w1.g4")


def _tests_read_all(ctx: Ctx) -> bool:
    """Whether a test reads ``__all__`` (the package ``__init__`` test of the old lazy-import scaffold)."""
    return any(
        "__all__" in p.read_text(encoding="utf-8", errors="ignore")
        for p in sorted((ctx.root / "tests").glob("**/*.py"))
    )


# --- g.5 / g.6 / g.1 / g.2 ------------------------------------------------------------------------------
_MAIN = 'from agent_connector_sdk import run\n\nif __name__ == "__main__":\n    run()\n'


@rule("w1.g5")
def g5(ctx: Ctx) -> None:
    path = ctx.pkg / "__main__.py"
    if not path.is_file() or path.read_text(encoding="utf-8") == _MAIN:
        return
    moved = (ctx.options.get(_G3_KEY) or {}).get("module", "")
    mcp = ctx.pkg / "mcp_server.py"
    if mcp.is_file() and "def get_mcp_instance" in mcp.read_text(encoding="utf-8"):
        return  # bootstrap kept, __main__ still valid
    tree = _parse(path.read_text(encoding="utf-8"))
    body = (
        [n for n in tree.body if not _doc(n) and not (isinstance(n, ast.ImportFrom) and n.module == "__future__")]
        if tree is not None
        else []
    )
    ok = len(body) == 2
    if ok:
        imp, main = body
        ok = (
            isinstance(imp, ast.ImportFrom)
            and (
                (imp.level == 0 and imp.module in (f"{ctx.pkg_name}.mcp_server", moved))
                or (imp.level == 1 and imp.module == "mcp_server")
            )
            and [a.name for a in imp.names] == ["mcp_server"]
            and isinstance(main, ast.If)
            and ast.dump(main.test) == ast.dump(_expr_of('__name__ == "__main__"'))
            and len(main.body) == 1
            and isinstance(main.body[0], ast.Expr)
            and _is_call(main.body[0].value, "mcp_server")
            and not main.body[0].value.args
            and not main.orelse
        )
    if not ok and "mcp_server" not in path.read_text(encoding="utf-8"):
        ctx.note(
            "w1.g5",
            "__main__.py runs the package's own command line, not the MCP server; left as is (the console script "
            "serves the connector)",
            ctx.rel(path),
        )
        return
    if not ok:
        ctx.note(
            "w1.g5",
            "__main__.py is not the plain `mcp_server()` entry; replace by hand with `run()`",
            ctx.rel(path),
            True,
        )
        return
    if not _declared(ctx):
        return
    ctx.write(ctx.rel(path), _MAIN, "w1.g5")


@rule("w1.g6")
def g6(ctx: Ctx) -> None:
    """The /health route lives inside get_mcp_instance and is deleted with it by g3; report a stray second one."""
    if ctx.options.get(_G3_KEY) is None:
        return
    for f in _py_files(ctx.pkg):
        if re.search(r"custom_route\(\s*[\"']/health[\"']", f.read_text(encoding="utf-8")):
            ctx.note(
                "w1.g6", "a /health route remains in the package; the SDK registers /health itself", ctx.rel(f), False
            )


def _toml_section(lines: list[str], header: str) -> tuple[int, int] | None:
    for i, line in enumerate(lines):
        if line.strip() == header:
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("["):
                j += 1
            while j - 1 > i and (not lines[j - 1].strip() or lines[j - 1].lstrip().startswith("#")):
                j -= 1  # blank and comment lines right above the next header belong to that header
            return i, j
    return None


def _array_end(lines: list[str], i: int) -> int:
    """Index of the line closing the TOML array that opens on line ``i``."""
    depth = 0
    for j in range(i, len(lines)):
        bare = re.sub(r'"[^"]*"|\'[^\']*\'', "", lines[j]).split("#")[0]
        depth += bare.count("[") - bare.count("]")
        if depth <= 0 and (j > i or "[" in bare):
            return j
    return len(lines) - 1


def _check_toml(ctx: Ctx, rule_id: str, text: str) -> bool:
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        ctx.note(rule_id, f"edited pyproject.toml would not parse ({err}); left untouched", "pyproject.toml", True)
        return False
    return True


def _entry_point_assertions(ctx: Ctx) -> None:
    """Tests asserting the entry-point table ``{FLEET: "<pkg>"}`` / ``{"<fleet>": "<pkg>"}`` follow the ``<pkg>:connector`` value."""
    pkg = re.escape(ctx.pkg_name)
    pattern = re.compile(rf'((?:\bFLEET|"{re.escape(ctx.fleet)}")\s*:\s*)"{pkg}"(\s*,?\s*\}})')
    for path in sorted((ctx.root / "tests").glob("**/*.py")):
        text = path.read_text(encoding="utf-8")
        new = pattern.sub(lambda m: f'{m.group(1)}"{ctx.pkg_name}:connector"{m.group(2)}', text)
        if new != text:
            ctx.write(ctx.rel(path), new, "w1.g1")


@rule("w1.g1")
def g1(ctx: Ctx) -> None:
    text = ctx.read("pyproject.toml")
    lines = text.split("\n")
    sec = _toml_section(lines, '[project.entry-points."agent_connector_sdk.connector"]')
    if sec is None:
        return
    for i in range(*sec):
        m = re.match(rf'^(\s*{re.escape(ctx.fleet)}\s*=\s*)"([^"]*)"(.*)$', lines[i])
        if not m:
            continue
        if m.group(2) == f"{ctx.pkg_name}:connector":
            return
        if m.group(2) != ctx.pkg_name:
            ctx.note("w1.g1", f"entry point value {m.group(2)!r} is not the bare package name", "pyproject.toml", True)
            return
        if not _declared(ctx):
            return  # g3/g4 reviewed
        lines[i] = f'{m.group(1)}"{ctx.pkg_name}:connector"{m.group(3)}'
        new = "\n".join(lines)
        if _check_toml(ctx, "w1.g1", new):
            ctx.write("pyproject.toml", new, "w1.g1")
            _entry_point_assertions(ctx)
        return


@rule("w1.g2")
def g2(ctx: Ctx) -> None:
    text = ctx.read("pyproject.toml")
    lines = text.split("\n")
    sec = _toml_section(lines, "[project.scripts]")
    if sec is None:
        return
    for i in range(*sec):
        m = re.match(rf'^(\s*{re.escape(ctx.fleet)}\s*=\s*)"([^"]*)"(.*)$', lines[i])
        if not m:
            continue
        value = m.group(2)
        if value == "agent_connector_sdk.cli:serve":
            return
        moved = (ctx.options.get(_G3_KEY) or {}).get("module", "")
        if value not in (
            f"{ctx.pkg_name}.mcp_server:mcp_server",
            f"{ctx.pkg_name}.__main__:main",
            f"{moved}:mcp_server",
        ):
            ctx.note("w1.g2", f"console script {value!r} is not the bootstrap function", "pyproject.toml", True)
            return
        if not _declared(ctx):
            return
        lines[i] = f'{m.group(1)}"agent_connector_sdk.cli:serve"{m.group(3)}'
        new = "\n".join(lines)
        if _check_toml(ctx, "w1.g2", new):
            ctx.write("pyproject.toml", new, "w1.g2")
        return


# --- k: version spelled once ---------------------------------------------------------------------------------
_VERSION_MODULES = {"__init__.py", "mcp_server.py", "api_client.py", "version.py", "_version.py"}


def _is_version_assign(n: ast.stmt) -> bool:
    if isinstance(n, ast.Assign):
        ok = len(n.targets) == 1 and ast.unparse(n.targets[0]) == "__version__"
    elif isinstance(n, ast.AnnAssign):
        ok = ast.unparse(n.target) == "__version__"
    else:
        return False
    return ok and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)


def _is_version_ref(e: ast.expr) -> bool:
    return isinstance(e, ast.Name) and e.id == "__version__" or isinstance(e, ast.Attribute) and e.attr == "__version__"


def _is_version_assert(n: ast.stmt) -> bool:
    """`assert [pkg.]__version__ == ...`, `... is not None`, or the bare truthiness `assert [pkg.]__version__`."""
    if not isinstance(n, ast.Assert):
        return False
    if _is_version_ref(n.test):
        return True
    t = n.test
    if isinstance(t, ast.Call) and isinstance(t.func, ast.Name) and not t.keywords:
        # presence checks: hasattr(m, "__version__"), isinstance(m.__version__, str)
        if t.func.id == "hasattr" and len(t.args) == 2:
            return isinstance(t.args[1], ast.Constant) and t.args[1].value == "__version__"
        if t.func.id == "isinstance" and len(t.args) == 2:
            return _is_version_ref(t.args[0])
    if (
        isinstance(t, ast.Compare)
        and len(t.ops) == 1
        and isinstance(t.ops[0], ast.Gt)
        and isinstance(t.left, ast.Call)
        and isinstance(t.left.func, ast.Name)
        and t.left.func.id == "len"
        and len(t.left.args) == 1
        and _is_version_ref(t.left.args[0])
        and isinstance(t.comparators[0], ast.Constant)
        and t.comparators[0].value == 0
    ):
        return True
    if not isinstance(n.test, ast.Compare) or len(n.test.ops) != 1 or not _is_version_ref(n.test.left):
        return False
    op, right = n.test.ops[0], n.test.comparators[0]
    return isinstance(op, ast.Eq) or (
        isinstance(op, ast.IsNot) and isinstance(right, ast.Constant) and right.value is None
    )


_PURE_ATTRS = {"loads", "import_module", "read_text", "read_bytes", "resolve", "joinpath", "parents", "parent"}


def _pure_setup(e: ast.expr) -> bool:
    """A read-only value: tomllib.loads / read_text / importlib.import_module / Path(...) chains over constants."""
    for n in ast.walk(e):
        if isinstance(n, ast.Call):
            f = n.func
            if not (
                isinstance(f, ast.Name) and f.id == "Path" or isinstance(f, ast.Attribute) and f.attr in _PURE_ATTRS
            ):
                return False
        elif isinstance(n, ast.Attribute):
            if n.attr not in _PURE_ATTRS and not (
                isinstance(n.value, ast.Name) and n.value.id in {"tomllib", "importlib"}
            ):
                return False
        elif not isinstance(
            n,
            ast.Name
            | ast.Constant
            | ast.JoinedStr
            | ast.FormattedValue
            | ast.BinOp
            | ast.Div
            | ast.Load
            | ast.Subscript
            | ast.Tuple
            | ast.keyword,
        ):
            return False
    return True


def _inside(node: ast.AST, spans: list[tuple[int, int]]) -> bool:
    line = getattr(node, "lineno", 0)
    return any(a <= line <= b for a, b in spans)


def _dead_setup(tree: ast.Module, spans: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], set[str], list[str]]:
    """Spans of pure assignments (and loops/functions left empty) that only fed the deleted assertions."""
    extra: list[tuple[int, int]] = []
    names: set[str] = set()
    dropped: list[str] = []
    fns = [f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef)]
    for fn in fns:
        fs = _span(fn)
        if _inside(fn, spans) or not any(fs[0] <= a and b <= fs[1] for a, b in spans):
            continue
        local = list(spans)
        changed = True
        while changed:
            changed = False
            loads = {
                n.id
                for n in ast.walk(fn)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and not _inside(n, local)
            }
            for n in ast.walk(fn):
                if _inside(n, local) or not isinstance(n, ast.stmt):
                    continue
                dead_assign = (
                    isinstance(n, ast.Assign)
                    and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)
                    and n.targets[0].id not in loads
                    and _pure_setup(n.value)
                )
                dead_loop = (
                    isinstance(n, ast.For | ast.AsyncFor)
                    and not n.orelse
                    and all(_inside(b, local) or _doc(b) for b in n.body)
                    and _pure_setup(n.iter)
                )
                if dead_assign or dead_loop:
                    local.append(_span(n))
                    names |= _name_loads([n])
                    changed = True
        body = [b for b in fn.body if not _doc(b)]
        if body and all(_inside(b, local) for b in body):
            extra.append(fs)
            names |= _name_loads([fn])
            dropped.append(fn.name)
        else:
            extra.extend(x for x in local if x not in spans)
    return extra, names, dropped


def _clean_version_asserts(text: str, dropped: list[str] | None = None) -> str:
    tree = _parse(text)
    if tree is None or "__version__" not in text:
        return text
    spans: list[tuple[int, int]] = []
    candidates: set[str] = set()
    parents: list[ast.AST] = [tree]
    for parent in ast.walk(tree):
        for attr in ("body", "orelse", "finalbody"):
            stmts = getattr(parent, attr, None)
            if not isinstance(stmts, list) or not stmts or not isinstance(stmts[0], ast.stmt):
                continue
            hits = [s for s in stmts if _is_version_assert(s)]
            if not hits:
                continue
            rest = [
                s for s in stmts if s not in hits and not _doc(s) and not isinstance(s, ast.Import | ast.ImportFrom)
            ]
            if not rest and isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef) and attr == "body":
                spans.append(_span(parent))
                candidates |= _name_loads([parent])
            elif not rest and not isinstance(parent, ast.Module):
                continue  # block would be empty: leave for review through the remaining reference scan
            else:
                for h in hits:
                    spans.append(_span(h))
                    candidates |= _name_loads([h])
    del parents
    # a class left with nothing but its docstring goes too
    for cls in (c for c in ast.walk(tree) if isinstance(c, ast.ClassDef)):
        body = [b for b in cls.body if not _doc(b)]
        if body and all(any(sp[0] <= _span(b)[0] and _span(b)[1] <= sp[1] for sp in spans) for b in body):
            spans.append(_span(cls))
    # drop spans nested in another span
    spans = [s for s in spans if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in spans)]
    if not spans:
        return text
    extra, more, gone = _dead_setup(tree, spans)
    spans += extra
    candidates |= more
    if dropped is not None:
        dropped.extend(gone)
    spans = [s for s in spans if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in spans)]
    return _prune_imports(_delete_spans(text, spans), candidates)


def _module_name(ctx: Ctx, f: Path) -> str:
    parts = list(f.relative_to(ctx.root).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _version_importers(ctx: Ctx, mod: str) -> list[tuple[Path, ast.ImportFrom]]:
    out = []
    for f in _py_files(ctx.root):
        tree = _parse(f.read_text(encoding="utf-8"))
        if tree is None:
            continue
        here = _module_name(ctx, f)
        pkg_of_here = here if f.name == "__init__.py" else here.rsplit(".", 1)[0] if "." in here else ""
        for n in ast.walk(tree):
            if not isinstance(n, ast.ImportFrom) or not any(a.name == "__version__" for a in n.names):
                continue
            target = n.module or ""
            if n.level:
                base = pkg_of_here.split(".")
                base = base[: len(base) - (n.level - 1)]
                target = ".".join([*base, *([n.module] if n.module else [])])
            if target == mod:
                out.append((f, n))
    return out


def _import_anchor(tree: ast.Module) -> int:
    """The line after which a new top-level import goes: the last top-level import, else the docstring, else 0."""
    end = 0
    for i, n in enumerate(tree.body):
        if isinstance(n, ast.Import | ast.ImportFrom) or (i == 0 and _doc(n)):
            end = max(end, n.end_lineno or n.lineno)
    return end


def _add_lines(text: str, lines: list[str], *, after: int | None = None) -> str:
    """Insert ``lines`` after line ``after`` (default: the import anchor of ``text``)."""
    tree = _parse(text)
    at = after if after is not None else (_import_anchor(tree) if tree is not None else 0)
    parts = text.split("\n")
    parts[at:at] = lines
    return "\n".join(parts)


def _replace_nodes(text: str, nodes: Sequence[ast.expr], new: str) -> str | None:
    """Replace single-line expression nodes by ``new``; ``None`` when one spans lines."""
    rows = text.split("\n")
    for node in sorted(nodes, key=lambda n: (n.lineno, n.col_offset), reverse=True):
        ln, col, eln, ecol = _pos(node)
        if ln != eln:
            return None
        line = rows[ln - 1].encode("utf-8")
        rows[ln - 1] = (line[:col] + new.encode() + line[ecol:]).decode("utf-8")
    return "\n".join(rows)


def _drop_from_all(text: str) -> str:
    """Remove the ``"__version__"`` entry from a literal top-level ``__all__``."""
    tree = _parse(text)
    if tree is None:
        return text
    for n in tree.body:
        target = n.targets[0] if isinstance(n, ast.Assign) and len(n.targets) == 1 else getattr(n, "target", None)
        if not (isinstance(n, ast.Assign | ast.AnnAssign) and isinstance(target, ast.Name) and target.id == "__all__"):
            continue
        if not isinstance(n.value, ast.List | ast.Tuple):
            continue
        keep = [e for e in n.value.elts if not (isinstance(e, ast.Constant) and e.value == "__version__")]
        if len(keep) == len(n.value.elts):
            continue
        n.value.elts = keep
        return _replace_span(text, n.lineno, n.end_lineno or n.lineno, ast.unparse(n))
    return text


def _all_names_version(tree: ast.Module) -> bool:
    for n in tree.body:
        value = n.value if isinstance(n, ast.Assign | ast.AnnAssign) else None
        if value is not None and "__all__" in ast.unparse(n).split("=")[0]:
            return any(isinstance(e, ast.Constant) and e.value == "__version__" for e in ast.walk(value))
    return False


def _metadata_alias(text: str) -> str:
    return "_v" if not re.search(r"\b_v\b", text) or re.search(r"import version as _v\b", text) else "_pkg_version"


_META_IMPORT = "from importlib.metadata import version as"


def _importer_rewrite(ctx: Ctx, imp_file: Path, node: ast.ImportFrom) -> None:
    """``from m import a, __version__`` keeps ``a`` and defines ``__version__`` from the installed metadata."""
    t = imp_file.read_text(encoding="utf-8")
    keep = [a for a in node.names if a.name != "__version__"]
    alias = _metadata_alias(t)
    t = _replace_span(t, node.lineno, node.end_lineno or node.lineno, _import_text(node, keep) if keep else "")
    t = _add_lines(t, [f"{_META_IMPORT} {alias}"] if f"{_META_IMPORT} {alias}" not in t else [])
    t = _add_lines(t, ["", f'__version__ = {alias}("{ctx.dist}")'])
    ctx.write(ctx.rel(imp_file), t, "w1.k1")


def _module_readers(rest: list[ast.stmt]) -> tuple[list[ast.expr], str | None]:
    """The ``__version__`` loads in a module's remaining body, or why they cannot be rewritten."""
    reads: list[ast.expr] = []
    for root in rest:
        for n in ast.walk(root):
            if isinstance(n, ast.Name) and n.id == "__version__":
                if isinstance(n.ctx, ast.Load):
                    reads.append(n)
                else:
                    return [], "`__version__` is assigned elsewhere in the module"
            elif isinstance(n, ast.Global | ast.Nonlocal) and "__version__" in n.names:
                return [], "`__version__` is declared global"
    return reads, None


def _test_files(ctx: Ctx) -> list[Path]:
    return [
        tf for tf in _py_files(ctx.root) if "tests" in tf.relative_to(ctx.root).parts or tf.name.startswith("test_")
    ]


def _module_aliases(tree: ast.AST, mod: str) -> set[str]:
    """Every spelling by which a file reaches module ``mod``: the dotted path, ``import mod as a``, ``from parent import leaf``
    and ``a = importlib.import_module("mod")`` (a test reads ``mcp_server.__version__`` through such a name)."""
    parent, _, leaf = mod.rpartition(".")
    names = {mod}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names |= {a.asname for a in n.names if a.name == mod and a.asname}
        elif isinstance(n, ast.ImportFrom) and parent and n.module == parent and n.level == 0:
            names |= {a.asname or a.name for a in n.names if a.name == leaf}
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            call = n.value
            if (
                isinstance(call, ast.Call)
                and ast.unparse(call.func) in ("importlib.import_module", "import_module")
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == mod
            ):
                names.add(n.targets[0].id)
    return names


def _version_reads(text: str, mod: str) -> list[ast.Attribute]:
    """The ``<module>.__version__`` attribute reads of ``mod`` in ``text``, whatever name the file binds the module to."""
    tree = _parse(text)
    if tree is None or "__version__" not in text:
        return []
    names = _module_aliases(tree, mod)
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and n.attr == "__version__" and ast.unparse(n.value) in names
    ]


@rule("w1.k1")
def k1(ctx: Ctx) -> None:
    for f in _py_files(ctx.pkg):
        if f.name not in _VERSION_MODULES and f.name != f"{ctx.pkg_name}.py":
            continue
        text = f.read_text(encoding="utf-8")
        tree = _parse(text)
        if tree is None or "__version__" not in text:
            continue
        hits = [n for n in tree.body if _is_version_assign(n)]
        if not hits:
            continue
        rel = ctx.rel(f)
        mod = _module_name(ctx, f)
        # tests: asserts are removed by k4 first
        tests = _test_files(ctx)
        for tf in tests:
            _clean_test_file(ctx, tf)
        rest = [n for n in tree.body if n not in hits]
        reads, why = _module_readers(rest)
        if why:
            ctx.note("w1.k1", f"{why}; rewrite that use by hand", rel, True)
            continue
        importers = _version_importers(ctx, mod)
        blocked = False
        rewrites: list[tuple[Path, ast.ImportFrom]] = []
        for imp_file, node in importers:
            is_test = imp_file in tests
            top_level = node.col_offset == 0 and sum(1 for i in importers if i[0] == imp_file) == 1
            if is_test or any(a.asname for a in node.names if a.name == "__version__") or not top_level:
                ctx.note("w1.k1", f"`__version__` of {mod} is imported here; rewrite by hand", ctx.rel(imp_file), True)
                blocked = True
            else:
                rewrites.append((imp_file, node))
        test_attr: list[Path] = []
        for tf in _py_files(ctx.root):
            if tf == f or not _version_reads(tf.read_text(encoding="utf-8"), mod):
                continue
            if tf in tests:
                test_attr.append(tf)
            else:
                ctx.note("w1.k1", f"`{mod}.__version__` is read here; rewrite by hand", ctx.rel(tf), True)
                blocked = True
        if _all_names_version(tree) and any(
            re.search(r"__all__", tf.read_text(encoding="utf-8")) for tf in tests if tf != f
        ):
            ctx.note("w1.k1", f"a test reads {mod}.__all__, which lists `__version__`; rewrite by hand", rel, True)
            blocked = True
        if blocked:
            continue
        for imp_file, node in rewrites:
            _importer_rewrite(ctx, imp_file, node)
        for tf in test_attr:
            tt = tf.read_text(encoding="utf-8")
            ttree = _parse(tt)
            if ttree is None:
                continue
            nodes = _version_reads(tt, mod)
            out = _replace_nodes(tt, nodes, f'importlib.metadata.version("{ctx.dist}")')
            if out is None:
                ctx.note("w1.k1", f"`{mod}.__version__` is read across lines here; rewrite by hand", ctx.rel(tf), True)
                continue
            if not re.search(r"^import importlib\.metadata$", out, re.M):
                out = _add_lines(out, ["import importlib.metadata"])
            ctx.write(ctx.rel(tf), _prune_imports(out, {mod.split(".")[0]}), "w1.k1")
        new_text = text
        if reads:
            alias = _metadata_alias(text)
            replaced = _replace_nodes(new_text, reads, f'{alias}("{ctx.dist}")')
            if replaced is None:
                ctx.note("w1.k1", "`__version__` is read across lines; rewrite that use by hand", rel, True)
                continue
            new_text = replaced
            if f"{_META_IMPORT} {alias}" not in new_text:
                new_text = _add_lines(new_text, [f"{_META_IMPORT} {alias}"])
        new_text = _drop_from_all(new_text)
        new_tree = _parse(new_text)
        if new_tree is None:
            ctx.note("w1.k1", "the rewritten module does not parse; rewrite by hand", rel, True)
            continue
        new_text = _delete_spans(new_text, [_span(n) for n in new_tree.body if _is_version_assign(n)])
        new_tree = _parse(new_text)
        only_docs = all(_doc(n) or isinstance(n, ast.Import | ast.ImportFrom) for n in (new_tree or tree).body)
        if f.name != "__init__.py" and (
            not new_text.strip() or (only_docs and new_tree is not None and not new_tree.body)
        ):
            ctx.delete(rel, "w1.k1")
        else:
            ctx.write(rel, new_text, "w1.k1")


_SEMVER = r"\d+\.\d+\.\d+"


@rule("w1.k2")
def k2(ctx: Ctx) -> None:
    rel = ".bumpversion.cfg"
    if not ctx.exists(rel):
        return
    text = ctx.read(rel)
    blocks: list[tuple[str, list[str]]] = []
    for line in text.split("\n"):
        if re.match(r"^\[.+\]\s*$", line):
            blocks.append((line.strip(), []))
        elif blocks:
            blocks[-1][1].append(line)
    heads = [b[0] for b in blocks]
    if "[bumpversion]" not in heads or "[bumpversion:file:pyproject.toml]" not in heads:
        ctx.note(
            "w1.k2", ".bumpversion.cfg has no [bumpversion] and pyproject.toml file section; left untouched", rel, False
        )
        return
    keep = [b for b in blocks if b[0] in ("[bumpversion]", "[bumpversion:file:pyproject.toml]")]
    out = "\n\n".join("\n".join([h, *[x for x in body]]).rstrip() for h, body in keep) + "\n"
    ctx.write(rel, out, "w1.k2")


@rule("w1.k3")
def k3(ctx: Ctx) -> None:
    files = [p for p in [ctx.root / "README.md", *sorted((ctx.root / "docs").rglob("*.md"))] if p.is_file()]
    line_re = re.compile(rf"^Package version: {_SEMVER}\.\s*$")
    cell_re = re.compile(rf"Version {_SEMVER};\s*")
    for f in files:
        old = f.read_text(encoding="utf-8")
        out = []
        for line in old.split("\n"):
            if line_re.match(line):
                continue
            if line.lstrip().startswith("|"):
                line = cell_re.sub("", line)
            out.append(line)
        new = "\n".join(out)
        ctx.write(ctx.rel(f), new, "w1.k3")


def _clean_test_file(ctx: Ctx, f: Path) -> None:
    old = f.read_text(encoding="utf-8")
    gone: list[str] = []
    new = _clean_version_asserts(old, gone)
    if new != old and not new.strip():
        ctx.delete(ctx.rel(f), "w1.k4")
    elif new != old:
        ctx.write(ctx.rel(f), new, "w1.k4")
    if gone:
        ctx.note("w1.k4", f"deleted test function(s) left with only dead setup: {', '.join(gone)}", ctx.rel(f))


@rule("w1.k4")
def k4(ctx: Ctx) -> None:
    for f in _py_files(ctx.root):
        parts = f.relative_to(ctx.root).parts
        if ("tests" in parts or f.name.startswith("test_")) and f.is_file():
            _clean_test_file(ctx, f)


# --- i: connector_sources becomes data only -------------------------------------------------------------
# The same assembly with annotated locals and the per-entry spec bound to a name first (28 fleet connectors).
_DECLARATION_TYPED = '''\
def declaration() -> IngestSourceDeclaration:
    """The declaration the server assembles from this module."""
    specs: list[IngestSourceSpec] = []
    for item in SOURCES:
        for entry in item["connector_sources"]:
            body: dict[str, Any] = {
                k: v for k, v in entry.items() if k not in ("tool", "mapping")
            }
            spec = {**body, "tools": (entry["tool"],)}
            specs.append(IngestSourceSpec.model_validate(spec))
    return IngestSourceDeclaration.model_validate(
        {
            "connector": CONNECTOR,
            "sources": specs,
            "schema_mappings": SCHEMA_MAPPINGS,
            "resources": RESOURCES,
        }
    )
'''


def _normal_declaration_src(node: ast.FunctionDef) -> str:
    """Source of ``node`` without its docstring and with annotated assignments read as plain ones."""
    fn = ast.parse(ast.unparse(node)).body[0]
    assert isinstance(fn, ast.FunctionDef)
    if fn.body and _doc(fn.body[0]):
        fn.body = fn.body[1:]

    class _Plain(ast.NodeTransformer):
        def visit_AnnAssign(self, n: ast.AnnAssign) -> ast.AST:
            self.generic_visit(n)
            return ast.Assign(targets=[n.target], value=n.value, lineno=n.lineno) if n.value else n

    return ast.unparse(ast.fix_missing_locations(_Plain().visit(fn)))


def _normal_declaration(node: ast.FunctionDef) -> str:
    return ast.dump(ast.parse(_normal_declaration_src(node)).body[0])


def _canonical_declaration() -> str:
    return ast.dump(ast.parse(_DECLARATION).body[0])


def _declaration_variant(node: ast.FunctionDef) -> str | None:
    """Which accepted assembly ``node`` is (equal to ``load_declaration``), else ``None``."""
    if ast.dump(node) == _canonical_declaration():
        return "standard"
    got = _normal_declaration(node)
    for name, src in (("standard", _DECLARATION), ("typed", _DECLARATION_TYPED)):
        fn = ast.parse(src).body[0]
        assert isinstance(fn, ast.FunctionDef)
        if got == _normal_declaration(fn):
            return name
    return None


def _declaration_difference(node: ast.FunctionDef) -> str:
    """The first statement where ``node`` departs from the closest accepted body, as written in the module."""
    got = ast.unparse(ast.parse(_normal_declaration_src(node)).body[0]).splitlines()
    best: tuple[float, str] = (-1.0, "")
    for src in (_DECLARATION, _DECLARATION_TYPED):
        fn = ast.parse(src).body[0]
        assert isinstance(fn, ast.FunctionDef)
        want = ast.unparse(ast.parse(_normal_declaration_src(fn)).body[0]).splitlines()
        matcher = difflib.SequenceMatcher(None, got, want, autojunk=False)
        extra = [g.strip() for tag, i1_, i2_, _, _ in matcher.get_opcodes() if tag != "equal" for g in got[i1_:i2_]]
        missing = [w.strip() for tag, _, _, j1_, j2_ in matcher.get_opcodes() if tag != "equal" for w in want[j1_:j2_]]
        detail = (
            f"`{extra[0]}` is not in the plain assembly" if extra else f"`{missing[0]}` is missing" if missing else ""
        )
        if matcher.ratio() > best[0]:
            best = (matcher.ratio(), detail)
    return best[1]


def _declaration_equal(node: ast.FunctionDef) -> bool:
    return _declaration_variant(node) is not None


def _rewrite_declaration_users(ctx: Ctx) -> tuple[dict[str, str], list[str]]:
    mod = f"{ctx.pkg_name}.connector_sources"
    own = ctx.pkg / "connector_sources.py"
    edits: dict[str, str] = {}
    bad: list[str] = []
    for f in _py_files(ctx.root):
        if f == own:
            continue
        text = f.read_text(encoding="utf-8")
        if "connector_sources" not in text:
            continue
        tree = _parse(text)
        if tree is None:
            continue
        decl_names: set[str] = set()
        const_names: set[str] = set()
        mod_names: set[str] = set()
        import_edits: list[tuple[int, int, str]] = []
        import_cols: list[int] = []  # indentation of each edited import (a nested import keeps its block)
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module == mod:
                keep = []
                for a in n.names:
                    if a.name == "declaration":
                        decl_names.add(a.asname or a.name)
                    elif a.name == "CONSTANT" or a.name == "CONNECTOR":
                        const_names.add(a.asname or a.name)
                    else:
                        keep.append(a)
                if len(keep) != len(n.names):
                    import_edits.append((n.lineno, n.end_lineno or n.lineno, _import_text(n, keep) if keep else ""))
                    import_cols.append(n.col_offset)
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module == ctx.pkg_name:
                keep = []
                for a in n.names:
                    if a.name == "connector_sources":
                        mod_names.add(a.asname or a.name)
                    keep.append(a)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name == mod and a.asname:
                        mod_names.add(a.asname)
        if not (decl_names or const_names or mod_names):
            continue
        reps: list[tuple[int, int, int, int, str]] = []  # (line, col, end_line, end_col, text)
        need_load = need_name = False
        parents: dict[int, ast.AST] = {}
        for p in ast.walk(tree):
            for c in ast.iter_child_nodes(p):
                parents[id(c)] = p
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and n.id in decl_names and isinstance(n.ctx, ast.Load):
                par = parents.get(id(n))
                if isinstance(par, ast.Call) and par.func is n and not par.args and not par.keywords:
                    reps.append((*_pos(par), f'load_declaration("{ctx.pkg_name}")'))
                    need_load = True
                else:
                    bad.append(f"{ctx.rel(f)}:{n.lineno} uses declaration other than as `declaration()`")
            elif isinstance(n, ast.Name) and n.id in const_names and isinstance(n.ctx, ast.Load):
                reps.append((*_pos(n), f'connector_name("{ctx.pkg_name}")'))
                need_name = True
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in mod_names:
                par = parents.get(id(n))
                if (
                    n.attr == "declaration"
                    and isinstance(par, ast.Call)
                    and par.func is n
                    and not par.args
                    and not par.keywords
                ):
                    reps.append((*_pos(par), f'load_declaration("{ctx.pkg_name}")'))
                    need_load = True
                elif n.attr == "CONNECTOR":
                    reps.append((*_pos(n), f'connector_name("{ctx.pkg_name}")'))
                    need_name = True
                else:
                    bad.append(f"{ctx.rel(f)}:{n.lineno} uses connector_sources.{n.attr}")
        if not (reps or import_edits):
            continue
        lines = text.split("\n")
        for ln, col, eln, ecol, new in sorted(reps, reverse=True):
            if ln != eln:
                bad.append(f"{ctx.rel(f)}:{ln} multi-line declaration call")
                continue
            line = lines[ln - 1].encode("utf-8")
            lines[ln - 1] = (line[:col] + new.encode() + line[ecol:]).decode("utf-8")
        text2 = "\n".join(lines)
        adds = []
        if need_load and "import load_declaration" not in text2:
            adds.append("from agent_connector_sdk.ingest import load_declaration")
        if need_name and "import connector_name" not in text2:
            adds.append("from agent_connector_sdk.connector_identity import connector_name")
        # imports: replace the first edited statement with the new imports; delete the rest
        ind = " " * (import_cols[import_edits.index(min(import_edits))] if import_edits else 0)
        if len(set(import_cols)) > 1:
            bad.append(f"{ctx.rel(f)}: connector_sources is imported at different nesting levels")
        first = True
        for start, end, repl in sorted(import_edits, key=lambda e: -e[0]):
            lines2 = text2.split("\n")
            del lines2[start - 1 : end]
            text2 = "\n".join(lines2)
        # re-insert: after the last future/top import line -> at the original first import location
        if adds:
            ins = min((e[0] for e in import_edits), default=None)
            keep_lines = [e[2] for e in import_edits if e[2]]
            block = "\n".join(ind + ln for ln in "\n".join([*adds, *keep_lines]).split("\n"))
            lines2 = text2.split("\n")
            at = (ins - 1) if ins else _first_import_line(tree)
            lines2[at:at] = block.split("\n")
            text2 = "\n".join(lines2)
        elif import_edits:
            lines2 = text2.split("\n")
            at = min(e[0] for e in import_edits) - 1
            lines2[at:at] = [ind + ln for e in import_edits if e[2] for ln in e[2].split("\n")]
            text2 = "\n".join(lines2)
        del first
        text2 = _prune_imports(text2, mod_names)
        edits[ctx.rel(f)] = text2
    return edits, bad


def _first_import_line(tree: ast.Module) -> int:
    for n in tree.body:
        if isinstance(n, ast.Import | ast.ImportFrom):
            return n.lineno - 1
    return 0


@rule("w1.i1")
def i1(ctx: Ctx) -> None:
    path = ctx.pkg / "connector_sources.py"
    if not path.is_file():
        return
    rel = ctx.rel(path)
    text = path.read_text(encoding="utf-8")
    tree = _parse(text)
    if tree is None:
        ctx.note("w1.i1", "connector_sources.py does not parse", rel, True)
        return
    decl = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "declaration"]
    if not decl:
        return
    if not _declaration_equal(decl[0]):
        ctx.note(
            "w1.i1",
            "declaration() is not a plain assembly of SOURCES/SCHEMA_MAPPINGS/RESOURCES (it does something else: "
            f"{_declaration_difference(decl[0])}); hand-migrate to load_declaration",
            rel,
            True,
        )
        return
    edits, bad = _rewrite_declaration_users(ctx)
    if bad:
        ctx.note("w1.i1", f"declaration()/CONNECTOR is used in a form the rule cannot rewrite: {bad}", rel, True)
        return
    for erel, etext in edits.items():
        ctx.write(erel, etext, "w1.i1")
    new = _delete_spans(text, [_span(decl[0])])
    cand = {"IngestSourceDeclaration", "IngestSourceSpec", "Any"}
    new_tree = _parse(new)
    if new_tree is not None:
        consts = [
            n
            for n in new_tree.body
            if (isinstance(n, ast.Assign) and len(n.targets) == 1 and ast.unparse(n.targets[0]) == "CONNECTOR")
            or (isinstance(n, ast.AnnAssign) and ast.unparse(n.target) == "CONNECTOR")
        ]
        if consts and "CONNECTOR" not in _name_loads(n for n in new_tree.body if n not in consts):
            new = _delete_spans(new, [_span(consts[0])])
    ctx.write(rel, _prune_imports(new, cand), "w1.i1")


def _emit(value: Any, indent: int) -> str:
    pad = "    " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        body = "".join(
            f"{pad}    {json.dumps(k, ensure_ascii=False)}: {_emit(v, indent + 1)},\n" for k, v in value.items()
        )
        return "{\n" + body + pad + "}"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_emit(v, indent) for v in value) + "]"
    return repr(value)


@rule("w1.i2")
def i2(ctx: Ctx) -> None:
    path = ctx.pkg / "connector_sources.py"
    if not path.is_file():
        return
    rel = ctx.rel(path)
    text = path.read_text(encoding="utf-8")
    tree = _parse(text)
    if tree is None:
        return
    if {"FIELD_SETS", "SCHEMA_VERSION"} & _top_defs(tree):
        return
    node = next(
        (
            n
            for n in tree.body
            if (isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "SCHEMA_MAPPINGS")
            or (isinstance(n, ast.AnnAssign) and ast.unparse(n.target) == "SCHEMA_MAPPINGS" and n.value is not None)
        ),
        None,
    )
    if node is None or node.value is None:
        return
    try:
        mappings = ast.literal_eval(node.value)
    except (ValueError, TypeError):
        ctx.note("w1.i2", "SCHEMA_MAPPINGS is not a literal; shared field sets not extracted", rel, False)
        return
    if not isinstance(mappings, dict) or not all(
        isinstance(m, dict) and isinstance(m.get("fields", {}), dict) for m in mappings.values()
    ):
        ctx.note("w1.i2", "SCHEMA_MAPPINGS has an unexpected shape; shared field sets not extracted", rel, False)
        return
    groups: dict[str, list[str]] = {}
    for key, m in mappings.items():
        if m.get("fields") and "field_sets" not in m:
            groups.setdefault(json.dumps(m["fields"], sort_keys=True), []).append(key)
    shared = {g: keys for g, keys in groups.items() if len(keys) >= 2}
    if not shared:
        return
    names: dict[str, str] = {}
    for key in mappings:  # numbered in order of first use
        for g, keys in shared.items():
            if key == keys[0]:
                names[g] = f"fields_{len(names) + 1}"
    field_sets = {names[g]: mappings[keys[0]]["fields"] for g, keys in shared.items()}
    out: dict[str, Any] = {}
    for key, m in mappings.items():
        gk = json.dumps(m.get("fields"), sort_keys=True) if m.get("fields") else None
        if gk in shared:
            out[key] = {
                ("field_sets" if k == "fields" else k): ([names[gk]] if k == "fields" else v) for k, v in m.items()
            }
        else:
            out[key] = m
    hint = f": {ast.unparse(node.annotation)}" if isinstance(node, ast.AnnAssign) else ""
    block = (
        f"SCHEMA_VERSION = 2\n\nFIELD_SETS{': dict[str, dict[str, str]]' if hint else ''} = {_emit(field_sets, 0)}"
        f"\n\nSCHEMA_MAPPINGS{hint} = {_emit(out, 0)}"
    )
    ctx.write(rel, _replace_span(text, node.lineno, node.end_lineno or node.lineno, block), "w1.i2")


# --- l: one entry point, content by convention --------------------------------------------------------------
_PROVIDER_GROUPS = {
    "agent_connector_sdk.skill_providers": "skills",
    "agent_connector_sdk.ontology_providers": "ontology",
    "agent_connector_sdk.source_connector_providers": "connectors",
}


@rule("w1.l1")
def l1(ctx: Ctx) -> None:
    text = ctx.read("pyproject.toml")
    lines = text.split("\n")
    changed = False
    for group, sub in _PROVIDER_GROUPS.items():
        sec = _toml_section(lines, f'[project.entry-points."{group}"]')
        if sec is None:
            continue
        start, end = sec
        entries = [ln for ln in lines[start + 1 : end] if ln.strip() and not ln.strip().startswith("#")]
        want = f"{ctx.pkg_name}.{sub}"
        ok = all((m := re.match(r'^\s*[\w.-]+\s*=\s*"([^"]*)"\s*$', e)) and m.group(1) == want for e in entries)
        if not ok:
            ctx.note(
                "w1.l1",
                f"{group} holds a non-conventional value (expected {want!r}); the group stays",
                "pyproject.toml",
                True,
            )
            continue
        s = start
        while (
            s > 0
            and lines[s - 1].startswith("#")
            and (lines[s - 1].startswith("# CONCEPT:") or "federation" in lines[s - 1].lower())
        ):
            s -= 1
        del lines[s:end]
        if s < len(lines) and s > 0:
            while s < len(lines) and not lines[s].strip() and not lines[s - 1].strip():
                del lines[s]
        changed = True
    if changed:
        new = "\n".join(lines)
        if _check_toml(ctx, "w1.l1", new):
            ctx.write("pyproject.toml", new, "w1.l1")


def _package_data_line(lines: list[str], pkg: str) -> int | None:
    sec = _toml_section(lines, "[tool.setuptools.package-data]")
    if sec is None:
        return None
    for i in range(*sec):
        if re.match(rf"^\s*{re.escape(pkg)}\s*=\s*\[", lines[i]):
            return i
    return None


@rule("w1.l2")
def l2(ctx: Ctx) -> None:
    markers = []
    for sub in ("skills", "prompts", "ontology", "connectors"):
        f = ctx.pkg / sub / "__init__.py"
        if f.is_file() and all(
            not ln.strip() or ln.strip().startswith("#") for ln in f.read_text(encoding="utf-8").split("\n")
        ):
            markers.append(sub)
    if not markers:
        return
    text = ctx.read("pyproject.toml")
    lines = text.split("\n")
    idx = _package_data_line(lines, ctx.pkg_name)
    missing = list(markers)
    new_text = text
    if idx is not None:
        end = _array_end(lines, idx)
        block = "\n".join(lines[idx : end + 1])
        missing = [s for s in markers if f'"{s}/' not in block]
    elif ctx.pyproject().get("tool", {}).get("setuptools", {}).get("package-data"):
        missing = list(markers)
    globs = {
        "skills": "skills/**/*",
        "prompts": "prompts/*.json",
        "ontology": "ontology/**/*",
        "connectors": "connectors/**/*",
    }
    if missing:
        if idx is None:
            ctx.note(
                "w1.l2",
                "no package-data entry for the package; markers kept so the content still ships",
                "pyproject.toml",
                True,
            )
            return
        extra = ", ".join(f'"{globs[s]}"' for s in missing)
        end = _array_end(lines, idx)
        close = lines[end]
        pos = close.rindex("]")
        before = close[:pos].rstrip()
        if before.strip() and not before.strip().endswith(("[", "=")) or end == idx:
            sep = "" if before.endswith(("[", ",")) else ","
            lines[end] = f"{before}{sep} {extra},{close[pos:]}"
        else:
            lines.insert(end, f"    {extra},")
        new_text = "\n".join(lines)
        if not _check_toml(ctx, "w1.l2", new_text):
            return
        ctx.write("pyproject.toml", new_text, "w1.l2")
    for sub in markers:
        ctx.delete(ctx.rel(ctx.pkg / sub / "__init__.py"), "w1.l2")


_SCAFFOLD_ATTRS = re.compile(
    r"\b(?:_MCP_AVAILABLE|_loaded_optional_modules|_expose_members|_import_module_safely|CORE_MODULES|OPTIONAL_MODULES)\b"
)


def _delete_scaffold_tests(ctx: Ctx) -> None:
    """Test functions that assert the deleted lazy-import scaffold (its flags and helpers) are deleted with it."""
    for f in _py_files(ctx.root):
        if "tests" not in f.relative_to(ctx.root).parts and not f.name.startswith("test_"):
            continue
        text = f.read_text(encoding="utf-8")
        tree = _parse(text)
        if tree is None or not _SCAFFOLD_ATTRS.search(text):
            continue
        lines = text.split("\n")
        hit = [
            t
            for t in _test_nodes(tree)
            if _SCAFFOLD_ATTRS.search("\n".join(lines[_span(t[1])[0] - 1 : _span(t[1])[1]]))
        ]
        if not hit:
            continue
        gone: list[ast.stmt] = [t[1] for t in hit]
        for cls in {id(t[2]): t[2] for t in hit if t[2] is not None}.values():
            left = [
                m
                for m in cls.body
                if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef) and m.name.startswith("test")
            ]
            if all(m in gone for m in left):
                gone = [g for g in gone if g not in cls.body]
                gone.append(cls)
        out, fixture_names = _prune_orphan_fixtures(_delete_nodes(text, gone))
        out = _prune_imports(out, _name_loads(gone) | fixture_names)
        if _SCAFFOLD_ATTRS.search(out):
            ctx.note("w1.l3", "scaffold names are still used outside the test functions", ctx.rel(f), True)
            continue
        if _has_test(out):
            ctx.write(ctx.rel(f), out, "w1.l3")
        else:
            ctx.delete(ctx.rel(f), "w1.l3")
        ctx.note(
            "w1.l3",
            f"deleted tests {[t[0] for t in hit]}: they assert the lazy-import scaffold that l3 deleted",
            ctx.rel(f),
            False,
        )


@rule("w1.l3")
def l3(ctx: Ctx) -> None:
    init = ctx.pkg / "__init__.py"
    if not init.is_file():
        return
    rel = ctx.rel(init)
    tree = _parse(init.read_text(encoding="utf-8"))
    if tree is None:
        return
    if _scaffold(tree) is not None:
        if not _declared(ctx):
            return  # g3/g4 did not migrate this package: the scaffold is still its import surface
        head = _remove_scaffold(ctx, "w1.l3")
        if head is not None:
            ctx.write(rel, head, "w1.l3")
        return
    odd = [
        n
        for n in tree.body
        if not (_doc(n) or isinstance(n, ast.Import | ast.ImportFrom) or _is_version_assign(n) or _is_connector(n))
    ]
    if odd:
        ctx.note(
            "w1.l3",
            f"__init__.py has content beyond the connector declaration (line {odd[0].lineno}); review",
            rel,
            False,
        )


def _is_connector(n: ast.stmt) -> bool:
    return isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "connector" for t in n.targets)


_DEP = re.compile(r'"(agent-connector-sdk)(\[[^\]]*\])?([^"]*)"')


@rule("w1.l4")
def l4(ctx: Ctx) -> None:
    text = ctx.read("pyproject.toml")
    lines = text.split("\n")
    data = ctx.pyproject()
    deps = data.get("project", {}).get("dependencies", [])
    hit = [d for d in deps if d.replace(" ", "").startswith("agent-connector-sdk")]
    if len(hit) != 1:
        ctx.note("w1.l4", f"expected one agent-connector-sdk dependency, found {len(hit)}", "pyproject.toml", True)
        return
    m = re.match(r"^agent-connector-sdk\s*(\[([^\]]*)\])?\s*([<>=!~][^;]*)?$", hit[0].strip())
    if not m:
        ctx.note("w1.l4", f"agent-connector-sdk requirement {hit[0]!r} has an unsupported form", "pyproject.toml", True)
        return
    opt = data.get("project", {}).get("optional-dependencies", {})
    drop = [
        k
        for k in ("mcp", "all")
        if k in opt and len(opt[k]) == 1 and opt[k][0].replace(" ", "").startswith("agent-connector-sdk")
    ]
    # the SDK extras of a dropped one-element extra (`mcp = ["agent-connector-sdk[mcp,stream]>=..."]`) move to the pin
    dropped_extras: set[str] = set()
    for key in drop:
        dm = re.match(r"^agent-connector-sdk\s*\[([^\]]*)\]", opt[key][0].strip())
        dropped_extras |= {e.strip() for e in (dm.group(1) if dm else "").split(",") if e.strip()}
    extras = sorted({e.strip() for e in (m.group(2) or "").split(",") if e.strip()} | dropped_extras | {"mcp"})
    pin = f"agent-connector-sdk[{','.join(extras)}]" + SDK_PIN.split("]", 1)[1]
    sec = _toml_section(lines, "[project]")
    assert sec is not None  # `dependencies` was read from [project] above
    dep_idx = [i for i in range(sec[0], sec[1]) if re.match(r"^\s*dependencies\s*=", lines[i])]
    if not dep_idx:
        ctx.note("w1.l4", "could not locate the dependencies array textually", "pyproject.toml", True)
        return
    i = dep_idx[0]
    j = _array_end(lines, i)
    for k in range(i, j + 1):
        lines[k] = _DEP.sub(lambda mm: f'"{pin}"', lines[k])
    # drop one-element mcp/all extras holding only the SDK requirement
    extras_sec = _toml_section(lines, "[project.optional-dependencies]")
    if extras_sec is not None:
        for key in drop:
            opt_sec = _toml_section(lines, "[project.optional-dependencies]")
            assert opt_sec is not None  # the header was found above and deletes only remove array lines
            s, e = opt_sec
            for a in range(s + 1, e):
                if re.match(rf"^\s*{key}\s*=\s*\[", lines[a]):
                    del lines[a : _array_end(lines, a) + 1]
                    break
        opt_sec = _toml_section(lines, "[project.optional-dependencies]")
        assert opt_sec is not None
        s, e = opt_sec
        if all(not ln.strip() or ln.strip().startswith("#") for ln in lines[s + 1 : e]):
            del lines[s:e]
    new = "\n".join(lines)
    if new != text and _check_toml(ctx, "w1.l4", new):
        ctx.write("pyproject.toml", new, "w1.l4")
    _drop_dangling_self_extras(ctx)
    _drop_undefined_sync_extras(ctx)
    _follow_pin_in_tests(ctx, hit[0].strip(), pin)


def _follow_pin_in_tests(ctx: Ctx, old: str, new: str) -> None:
    """A test that asserts the connector's SDK requirement string follows the pin l4 wrote (``test_sdk_floor_...``)."""
    if old == new:
        return
    for path in sorted((ctx.root / "tests").glob("**/*.py")):
        text = path.read_text(encoding="utf-8")
        fixed = text
        for quote in ('"', "'"):
            fixed = fixed.replace(f"{quote}{old}{quote}", f"{quote}{new}{quote}")
        if fixed != text:
            ctx.write(ctx.rel(path), fixed, "w1.l4")


_SYNC_ARGS = re.compile(r"(?m)^(\s*sync-args:\s*)(.+?)\s*$")
_SYNC_EXTRA = re.compile(r"\s*--extra[ =]([A-Za-z0-9_.-]+)")


def _drop_undefined_sync_extras(ctx: Ctx) -> None:
    """A caller workflow's ``sync-args`` naming an extra l4 deleted makes ``uv sync`` fail ("Extra `mcp` is not defined").

    The repo's own PR gate passes ``--extra mcp`` to ``uv sync``; once the one-element ``mcp`` extra is gone the flag goes too.
    """
    defined = set(ctx.pyproject().get("project", {}).get("optional-dependencies", {}))
    wf_dir = ctx.root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return
    for path in sorted(wf_dir.glob("*.yml")):
        rel = ctx.rel(path)
        text = path.read_text(encoding="utf-8")

        def fix(m: re.Match[str]) -> str:
            args = _SYNC_EXTRA.sub(lambda e: e.group(0) if e.group(1) in defined else "", m.group(2)).strip()
            return m.group(1) + args if args else m.group(0)

        new = _SYNC_ARGS.sub(fix, text)
        if new != text:
            ctx.write(rel, new, "w1.l4")


_SELF_EXTRA = re.compile(r"^(\s*)([A-Za-z0-9_.-]+)\s*\[([^\]]+)\](.*)$")


def _drop_dangling_self_extras(ctx: Ctx) -> None:
    """A self-reference to an extra that no longer exists fails the release readiness check ("unknown transitive extra").

    ``all = ["<dist>[mcp]"]`` after l4 deleted ``mcp``: the undefined extra leaves the entry's bracket list
    (``<dist>[mcp,postgres]`` becomes ``<dist>[postgres]``), and an entry left with no extras goes, an emptied extra with it.
    """
    text = ctx.read("pyproject.toml")
    data = ctx.pyproject()
    opt = data.get("project", {}).get("optional-dependencies", {})
    dist = re.sub(r"[-_.]+", "-", ctx.dist).lower()
    defined = set(opt)
    rewritten: dict[str, list[str]] = {}
    for key, items in opt.items():
        out: list[str] = []
        changed = False
        for item in items:
            m = _SELF_EXTRA.match(item)
            if m and re.sub(r"[-_.]+", "-", m.group(2)).lower() == dist:
                names = [e.strip() for e in m.group(3).split(",") if e.strip()]
                kept = [e for e in names if e in defined]
                if len(kept) != len(names):
                    changed = True
                    if kept:
                        out.append(f"{m.group(2)}[{','.join(kept)}]{m.group(4)}")
                    continue
            out.append(item)
        if changed:
            rewritten[key] = out
    if not rewritten:
        return
    lines = text.split("\n")
    for key, items in rewritten.items():
        sec = _toml_section(lines, "[project.optional-dependencies]")
        if sec is None:
            return
        for a in range(sec[0] + 1, sec[1]):
            if re.match(rf"^\s*{re.escape(key)}\s*=\s*\[", lines[a]):
                end = _array_end(lines, a)
                if items:
                    lines[a : end + 1] = [f"{key} = [ " + ", ".join(f'"{i}"' for i in items) + ",]"]
                else:
                    del lines[a : end + 1]
                break
    sec = _toml_section(lines, "[project.optional-dependencies]")
    if sec is not None and all(not ln.strip() or ln.strip().startswith("#") for ln in lines[sec[0] + 1 : sec[1]]):
        del lines[sec[0] : sec[1]]
    new = "\n".join(lines)
    if new != text and _check_toml(ctx, "w1.l4", new):
        ctx.write("pyproject.toml", new, "w1.l4")


# --- g.7 tests importing the deleted functions ------------------------------------------------------------
def _runs_bootstrap_module(n: ast.AST, mod: str) -> bool:
    """``runpy.run_module("<pkg>.mcp_server", run_name="__main__")``: the deleted ``__main__`` bootstrap."""
    if not (isinstance(n, ast.Call) and n.args):
        return False
    fn = n.func
    name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
    first = n.args[0]
    return name == "run_module" and isinstance(first, ast.Constant) and first.value == mod


def _deleted_symbol_users_in(ctx: Ctx, text: str) -> list[str]:
    """The deleted names the code uses; a name only mentioned in a docstring or comment is not a use."""
    tree = _parse(text)
    if tree is None:
        return []
    hits: list[str] = []
    mod = f"{ctx.pkg_name}.mcp_server"
    docs = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr)}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module in (mod, ctx.pkg_name):
            hits += [a.name for a in n.names if a.name in ("get_mcp_instance", "mcp_server")]
            if n.module == mod:
                hits += [a.name for a in n.names if a.name == "__version__"]
        elif (
            (isinstance(n, ast.Name) and n.id == "get_mcp_instance")
            or (isinstance(n, ast.Attribute) and n.attr == "get_mcp_instance")
            or (
                isinstance(n, ast.Constant)
                and isinstance(n.value, str)
                and id(n) not in docs
                and re.search(r"\bget_mcp_instance\b", n.value)
            )
        ):
            hits.append("get_mcp_instance")
        elif _runs_bootstrap_module(n, mod):
            hits.append("run_module(mcp_server)")
        elif (
            isinstance(n, ast.Attribute)
            and n.attr == "mcp_server"
            and not (isinstance(n.value, ast.Name) and n.value.id == ctx.pkg_name)
        ):
            hits.append("mcp_server")  # `module.mcp_server` on an imported bootstrap module
    return sorted(set(hits))


def _deleted_symbol_users(ctx: Ctx, f: Path) -> list[str]:
    return _deleted_symbol_users_in(ctx, f.read_text(encoding="utf-8"))


_BUILD_IMPORT = "from agent_connector_sdk.connector import build_server"


def _scope_of(node: ast.AST, parents: dict[ast.AST, ast.AST], tree: ast.Module) -> ast.AST:
    cur: ast.AST | None = parents.get(node)
    while cur is not None:
        if isinstance(cur, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            return cur
        cur = parents.get(cur)
    return tree


def _splice(text: str, node: ast.stmt | ast.expr, new: str) -> str:
    """Replace the exact source segment of ``node`` with ``new`` (later lines keep the node's indentation)."""
    assert node.end_lineno is not None and node.end_col_offset is not None
    lines = text.split("\n")
    first, last = lines[node.lineno - 1].encode(), lines[node.end_lineno - 1].encode()
    pad = " " * node.col_offset
    head = first[: node.col_offset].decode()
    tail = last[node.end_col_offset :].decode()
    body = new.split("\n")
    body = [body[0], *[pad + ln for ln in body[1:]]]
    lines[node.lineno - 1 : node.end_lineno] = (head + "\n".join(body) + tail).split("\n")
    return "\n".join(lines)


def _build_server_targets(target: ast.expr, scope: ast.AST) -> tuple[str | None, str | None]:
    """The new ``args, mcp`` targets for an old ``(mcp, args, middlewares[, tags])`` unpack, or (None, reason)."""
    if not isinstance(target, ast.Tuple):
        return None, "assigns the result to a single name"
    elts = list(target.elts)
    stars = [e for e in elts if isinstance(e, ast.Starred)]
    plain = [e for e in elts if isinstance(e, ast.Name)]
    if len(plain) + len(stars) != len(elts) or len(stars) > 1 or (stars and not isinstance(elts[-1], ast.Starred)):
        return None, "unpacks into something other than plain names (star only last)"
    if (not stars and len(plain) not in (3, 4)) or not plain or len(plain) > 4:
        return None, f"unpacks {len(plain)} values, not the old (mcp, args, middlewares[, tags]) shape"
    loads = {n.id for n in ast.walk(scope) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    rest = [e.id for e in plain[2:]] + [e.value.id for e in stars if isinstance(e.value, ast.Name)]
    read = [n for n in rest if n in loads]
    if read:
        return None, f"reads {read} (middlewares or tags), which build_server does not return"
    args_n = plain[1].id if len(plain) > 1 and plain[1].id in loads else "_"
    return f"{args_n}, {plain[0].id}", None


def _is_instance_call(node: ast.AST) -> TypeGuard[ast.Call]:
    """``get_mcp_instance()`` or ``<name>.get_mcp_instance()``."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    return (isinstance(f, ast.Name) and f.id == "get_mcp_instance") or (
        isinstance(f, ast.Attribute) and f.attr == "get_mcp_instance" and isinstance(f.value, ast.Name)
    )


def _argv_of(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> tuple[str, str | None]:
    """The ``command_args`` source for a call: the literal ``sys.argv`` an enclosing ``with`` patches, else ``[]``."""
    cur: ast.AST | None = parents.get(node)
    while cur is not None:
        if isinstance(cur, ast.With | ast.AsyncWith):
            for item in cur.items:
                ex = item.context_expr
                if not (isinstance(ex, ast.Call) and "argv" in ast.unparse(ex)):
                    continue
                val = ex.args[-1] if ex.args else None
                if (
                    isinstance(val, ast.List)
                    and val.elts
                    and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in val.elts)
                ):
                    return repr([e.value for e in val.elts[1:] if isinstance(e, ast.Constant)]), None
                return "[]", "patches sys.argv with something other than a literal list of strings"
        cur = parents.get(cur)
    return "[]", None


def _note_receiver(
    call: ast.Call, _stmt: ast.AST, _parents: dict[ast.AST, ast.AST], _tree: ast.Module, receivers: set[str]
) -> None:
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        receivers.add(call.func.value.id)


def _is_module_import(stmt: ast.stmt, name: str) -> bool:
    """``name = importlib.import_module("...")`` (or ``import_module``)."""
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)):
        return False
    call = stmt.value
    return (
        stmt.targets[0].id == name
        and isinstance(call, ast.Call)
        and len(call.args) == 1
        and not call.keywords
        and ast.unparse(call.func) in ("importlib.import_module", "import_module")
    )


def _drop_unused_receivers(text: str, receivers: set[str]) -> str:
    """Delete ``name = importlib.import_module(...)`` for receivers nothing reads any more."""
    tree = _parse(text)
    if tree is None or not receivers:
        return text
    loads = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    dead = [
        n for n in ast.walk(tree) if isinstance(n, ast.stmt) and any(_is_module_import(n, r) for r in receivers - loads)
    ]
    if not dead:
        return text
    return _prune_imports(_delete_nodes(text, dead), {"importlib", "import_module"})


def _rewrite_server_test(ctx: Ctx, text: str) -> tuple[str | None, list[str]]:
    """Rewrite the ``get_mcp_instance()`` unpack form to ``build_server``; (new text | None, blocking reasons)."""
    tree = _parse(text)
    if tree is None:
        return None, []
    mod = f"{ctx.pkg_name}.mcp_server"
    parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    edits: list[tuple[ast.stmt | ast.expr, str]] = []
    problems: list[str] = []
    handled: set[ast.AST] = set()
    receivers: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module == mod:
            hit = [a for a in n.names if a.name == "get_mcp_instance"]
            if not hit:
                continue
            if hit[0].asname:
                problems.append(f"line {n.lineno}: imports get_mcp_instance under an alias")
                continue
            keep = [a for a in n.names if a.name != "get_mcp_instance"]
            pad = " " * n.col_offset
            new = _BUILD_IMPORT if not keep else _import_text(n, keep) + "\n" + pad + _BUILD_IMPORT
            edits.append((n, new))
    for n in ast.walk(tree):
        if not _is_instance_call(n):
            continue
        handled.add(n.func)
        if n.args or n.keywords:
            problems.append(f"line {n.lineno}: calls get_mcp_instance with arguments")
            continue
        up = parents.get(n)
        argv, why = _argv_of(n, parents)
        if why is not None:
            problems.append(f"line {n.lineno}: {why}")
            continue
        call = f'build_server("{ctx.pkg_name}", command_args={argv})'
        if isinstance(up, ast.Assign) and up.value is n and len(up.targets) == 1:
            tgt, why = _build_server_targets(up.targets[0], _scope_of(up, parents, tree))
            if tgt is None:
                problems.append(f"line {n.lineno}: {why}")
                continue
            edits.append((up, f"{tgt} = {call}"))
            _note_receiver(n, up, parents, tree, receivers)
        elif (
            isinstance(up, ast.Subscript)
            and up.value is n
            and isinstance(up.slice, ast.Constant)
            and up.slice.value in (0, 1)
        ):
            edits.append((up, f"{call}[{1 - up.slice.value}]"))
            _note_receiver(n, up, parents, tree, receivers)
        else:
            problems.append(
                f"line {n.lineno}: uses the get_mcp_instance() result other than as `<targets> = ...` or `[0]`/`[1]`"
            )
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id == "get_mcp_instance" and n not in handled:
            problems.append(f"line {n.lineno}: references get_mcp_instance outside `<targets> = get_mcp_instance()`")
        elif _is_call(n, "mcp_server"):
            problems.append(f"line {n.lineno}: calls mcp_server() directly")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith(mod + "."):
            problems.append(f"line {n.lineno}: patches {n.value!r}; build_server does not read the module's names")
    if problems:
        return None, problems
    out = text
    for node, new in sorted(edits, key=lambda e: (e[0].lineno, e[0].col_offset), reverse=True):
        out = _splice(out, node, new)
    if edits and _BUILD_IMPORT not in out:
        out = _add_lines(out, [_BUILD_IMPORT])
    out = _drop_unused_receivers(out, receivers)
    left = _deleted_symbol_users_in(ctx, out)
    return (out, []) if not left else (None, [f"still uses {left} after the rewrite"])


_G7_REASON = "tests the bootstrap the SDK now owns; covered by the connector_conformance startup check"


def _test_nodes(tree: ast.Module) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef, ast.ClassDef | None]]:
    """Test functions at module level and in module-level classes: (display name, node, owning class)."""
    out: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef, ast.ClassDef | None]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test"):
            out.append((node.name, node, None))
        elif isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef) and m.name.startswith("test"):
                    out.append((f"{node.name}.{m.name}", m, node))
    return out


def _has_test(text: str) -> bool:
    tree = _parse(text)
    return tree is not None and bool(_test_nodes(tree))


def _is_fixture(node: ast.stmt) -> bool:
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return False
    return any("fixture" in ast.unparse(d) for d in node.decorator_list)


def _delete_nodes(text: str, nodes: Iterable[ast.stmt]) -> str:
    return _delete_spans(text, [_span(n) for n in nodes])


def _prune_orphan_fixtures(text: str) -> tuple[str, set[str]]:
    """Delete module-level fixtures nothing requests any more (not autouse); returns (text, names they loaded)."""
    loaded: set[str] = set()
    while True:
        tree = _parse(text)
        if tree is None:
            return text, loaded
        wanted = {
            a.arg for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) for a in n.args.args
        }
        wanted |= _name_loads([tree])
        dead = [
            n
            for n in tree.body
            if _is_fixture(n)
            and isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            and "autouse" not in "".join(ast.unparse(d) for d in n.decorator_list)
            and n.name not in wanted
        ]
        if not dead:
            return text, loaded
        loaded |= _name_loads(dead)
        text = _delete_nodes(text, dead)


def _delete_unexpressible_tests(ctx: Ctx, text: str) -> tuple[str | None, list[str]]:
    """Delete the test functions that use the deleted bootstrap in ways ``build_server`` cannot express.

    Returns (new text, deleted test names); (None, []) when an offending use sits outside the test functions
    (module level, a fixture, a helper) or the rewrite still fails: the file is then left alone.
    """
    tree = _parse(text)
    if tree is None:
        return None, []
    mod = f"{ctx.pkg_name}.mcp_server"
    use = re.compile(rf"\bget_mcp_instance\b|\bmcp_server\b|{re.escape(mod)}\.")
    lines = text.split("\n")
    cands = [t for t in _test_nodes(tree) if use.search("\n".join(lines[_span(t[1])[0] - 1 : _span(t[1])[1]]))]
    if not cands:
        return None, []

    def without(drop: Iterable[ast.stmt]) -> str:
        return _delete_nodes(text, drop)

    # a candidate the recipe can rewrite on its own (every other candidate removed) is kept and rewritten
    doomed: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef, ast.ClassDef | None]] = []
    for item in cands:
        others = [c[1] for c in cands if c is not item]
        new, _problems = _rewrite_server_test(ctx, without(others))
        if new is None:
            doomed.append(item)
    if not doomed:
        return None, []
    gone: list[ast.stmt] = [d[1] for d in doomed]
    for cls in {id(d[2]): d[2] for d in doomed if d[2] is not None}.values():
        left = [
            m for m in cls.body if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef) and m.name.startswith("test")
        ]
        if all(m in gone for m in left):
            gone = [g for g in gone if g not in cls.body]
            gone.append(cls)
    names = [d[0] for d in doomed]
    out, fixture_names = _prune_orphan_fixtures(without(gone))
    out = _prune_imports(out, _name_loads(gone) | fixture_names | {"get_mcp_instance", "mcp_server"})
    rewritten, _problems = _rewrite_server_test(ctx, out)
    if rewritten is None:
        return None, []
    return rewritten, names


@rule("w1.g7")
def g7(ctx: Ctx) -> None:
    mcp = ctx.pkg / "mcp_server.py"
    if not mcp.is_file() or "def get_mcp_instance" in mcp.read_text(encoding="utf-8"):
        return
    table = fingerprint_table(ctx)
    for f in _py_files(ctx.root):
        if "tests" not in f.relative_to(ctx.root).parts and not f.name.startswith("test_"):
            continue
        used = _deleted_symbol_users(ctx, f)
        if not used:
            continue
        text = f.read_text(encoding="utf-8")
        if (
            f.name in SCAFFOLD_TESTS
            and f.parent == ctx.root / "tests"
            and fingerprint(ctx, text) in table.get(f.name, ())
        ):
            continue  # rule h deletes it
        new, problems = _rewrite_server_test(ctx, text)
        if new is not None:
            ctx.write(ctx.rel(f), new, "w1.g7")
            continue
        trimmed, deleted = _delete_unexpressible_tests(ctx, text)
        if trimmed is not None:
            if _has_test(trimmed):
                ctx.write(ctx.rel(f), trimmed, "w1.g7")
            else:
                ctx.delete(ctx.rel(f), "w1.g7")
            ctx.note("w1.g7", f"deleted tests {deleted}: {_G7_REASON}", ctx.rel(f), False)
            continue
        why = "; ".join(problems[:3]) + (f"; and {len(problems) - 3} more" if len(problems) > 3 else "")
        ctx.note(
            "w1.g7",
            f"test uses {used}: {why or 'not the rewritable shape'}. Rewrite by hand with "
            f'agent_connector_sdk.connector.build_server("{ctx.pkg_name}", command_args=[...]) which returns (args, mcp)',
            ctx.rel(f),
            True,
        )


# --- h: scaffold tests by fingerprint --------------------------------------------------------------------
def normalise(ctx_names: Iterable[str], text: str) -> str:
    """Placeholder names and semvers; drop blank lines and comment lines. ``ctx_names`` is (repo, fleet, pkg)."""
    repo, fleet, pkg = ctx_names
    subs: dict[str, str] = {}
    for name, token in ((repo, "{REPO}"), (fleet, "{FLEET}"), (pkg, "{PKG}")):
        if not name:
            continue
        for variant, tok in (
            (name, token),
            (name.replace("-", "_"), "{PKG}"),
            (name.upper(), token + "_UP"),
            (name.upper().replace("-", "_"), "{PKG}_UP"),
            (name.title().replace("-", ""), token + "_TITLE"),
        ):
            subs.setdefault(variant, tok)
    for variant in sorted(subs, key=len, reverse=True):
        text = text.replace(variant, subs[variant])
    text = re.sub(r"\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.]+)?", "{SEMVER}", text)
    out = [ln.rstrip() for ln in text.split("\n") if ln.strip() and not ln.strip().startswith("#")]
    return "\n".join(out)


def digest(normalised: str) -> str:
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]


def fingerprint(ctx: Ctx, text: str) -> str:
    return digest(normalise((ctx.dist, ctx.fleet, ctx.pkg_name), text))


def fingerprint_table(ctx: Ctx) -> dict[str, list[str]]:
    given = ctx.options.get("fingerprints")
    if given is not None:
        return given
    if FINGERPRINTS_PATH.is_file():
        return json.loads(FINGERPRINTS_PATH.read_text(encoding="utf-8"))
    return {}


_ENV_KEY = "KNOWLEDGE_GRAPH_SYNC_BACKGROUND"


def _is_env_assign(n: ast.stmt) -> bool:
    return (
        isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and ast.unparse(n.targets[0]) in (f'os.environ["{_ENV_KEY}"]', f"os.environ['{_ENV_KEY}']")
    )


@rule("w1.h")
def h(ctx: Ctx) -> None:
    table = fingerprint_table(ctx)
    tests = ctx.root / "tests"
    for name in SCAFFOLD_TESTS:
        f = tests / name
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        fp = fingerprint(ctx, text)
        rel = ctx.rel(f)
        if fp not in table.get(name, ()):
            ctx.note("w1.h", f"{name} matches no scaffold fingerprint (hash {fp}); left in place", rel, False)
            continue
        if name == "test_ontology_parent_link.py" and "PENDING_NEW_PARENT" in text:
            if not re.search(r"^PENDING_NEW_PARENT\b[^=\n]*=\s*frozenset\(\s*\)\s*$", text, re.M):
                ctx.note("w1.h", "PENDING_NEW_PARENT is not empty; the plugin has no pending allowance", rel, False)
                continue
        ctx.delete(rel, "w1.h")
    conf = tests / "conftest.py"
    if conf.is_file():
        text = conf.read_text(encoding="utf-8")
        tree = _parse(text)
        if tree is not None and any(_is_env_assign(n) for n in tree.body):
            rest = [n for n in tree.body if not _is_env_assign(n)]
            plain = all(_doc(n) or (isinstance(n, ast.Import) and [a.name for a in n.names] == ["os"]) for n in rest)
            rel = ctx.rel(conf)
            if plain:
                ctx.delete(rel, "w1.h")
            else:
                new = _delete_spans(text, [_span(n) for n in tree.body if _is_env_assign(n)])
                ctx.write(rel, _prune_imports(new, {"os"}), "w1.h")
