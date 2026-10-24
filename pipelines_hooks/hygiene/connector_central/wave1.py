"""Wave 1 rules: server bootstrap, scaffold tests, version, ingest declaration, entry points (PIPE-GATES-R016.50-.67).

Source: ``plans/connector-sdk-wave1-codemod-rules-2026-10-23.md``. Every rule requires the full pre-migration shape and
otherwise records a review item and leaves the files untouched. ``ORDER`` is the run order; ``ORDER_LAST`` runs after
the ingest rules (the scaffold tests are fingerprinted last so rewritten imports are final).
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import re
import tomllib
from collections.abc import Iterable
from pathlib import Path
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
_G3_KEY = "_w1_g3"


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


def _analyse_instance(fn: ast.FunctionDef, local_funcs: dict[str, ast.FunctionDef]) -> dict[str, Any]:
    body = list(fn.body)
    if body and _doc(body[0]):
        body = body[1:]
    info: dict[str, Any] = {"health": False, "env": [], "tags": None, "extra": []}
    env = [(s, _env_key(s)) for s in body]
    info["env"] = [k for _s, k in env if k]
    body = [s for s, k in env if not k]
    i = 0

    def bad(stmt: ast.stmt, why: str = "is outside the allowed bootstrap statements") -> _Reject:
        return _Reject(f"line {stmt.lineno}: `{ast.unparse(stmt)[:70]}` {why}")

    head = body[i] if i < len(body) else None
    if isinstance(head, ast.Expr) and _is_call(head.value, "load_config"):
        if head.value.args or head.value.keywords:
            raise bad(head)
        i += 1
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
    kw = {k.arg: k.value for k in call.keywords}
    if call.args or None in kw or set(kw) - {"name", "version", "instructions"}:
        raise bad(stmt, "passes arguments beyond name, version and instructions to create_mcp_server")
    version = kw.get("version")
    if not (isinstance(version, ast.Name) and version.id == "__version__"):
        raise bad(stmt, "does not pass version=__version__")
    if "instructions" not in kw:
        raise bad(stmt, "has no instructions=")
    info["instructions"] = kw["instructions"]
    info["mcp"] = mcp_n
    i += 1
    route = body[i] if i < len(body) else None
    if isinstance(route, ast.AsyncFunctionDef | ast.FunctionDef) and route.decorator_list:
        d = route.decorator_list[0]
        ok = (
            len(route.decorator_list) == 1
            and isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr == "custom_route"
            and isinstance(d.func.value, ast.Name)
            and d.func.value.id == mcp_n
            and d.args
            and isinstance(d.args[0], ast.Constant)
            and d.args[0].value == "/health"
        )
        rbody = [s for s in route.body if not _doc(s)]
        if not (ok and len(rbody) == 1 and isinstance(rbody[0], ast.Return)):
            raise bad(route, "is not the plain /health route")
        info["health"] = True
        i += 1
    if i >= len(body):
        raise _Reject("no register_tool_surface call")
    stmt = body[i]
    if (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
        and _is_call(stmt.value, "register_tool_surface")
    ):
        info["tags"] = stmt.targets[0].id
        call = stmt.value
    elif isinstance(stmt, ast.Expr) and _is_call(stmt.value, "register_tool_surface"):
        call = stmt.value
    else:
        raise bad(stmt)
    if len(call.args) != 1 or not (isinstance(call.args[0], ast.Name) and call.args[0].id == mcp_n):
        raise bad(stmt, "does not pass the server as the only positional argument")
    kw = {k.arg: k.value for k in call.keywords}
    allowed = {"client_cls", "get_client", "service", "tools_module", *_SURFACE_KWARGS}
    if None in kw or set(kw) - allowed:
        raise bad(stmt, f"passes unsupported keywords {sorted(k for k in kw if k and k not in allowed)}")
    for need in ("client_cls", "get_client"):
        if not isinstance(kw.get(need), ast.Name):
            raise bad(stmt, f"does not pass {need} as a plain name")
    if "tools_module" in kw and ast.dump(kw["tools_module"]) != ast.dump(_expr_of("sys.modules[__name__]")):
        raise bad(stmt, "passes a tools_module other than sys.modules[__name__]")
    info["surface"] = kw
    i += 1
    while i < len(body):
        extra = _bare_call(body[i])
        if extra is None or not isinstance(extra.func, ast.Name) or _is_call(extra, "register_tool_surface"):
            break
        name = extra.func.id
        if not (
            len(extra.args) == 1
            and not extra.keywords
            and isinstance(extra.args[0], ast.Name)
            and extra.args[0].id == mcp_n
        ):
            break
        target = local_funcs.get(name)
        if target is None or not _one_param(target):
            raise bad(
                body[i],
                f"calls `{name}`, which is not a top-level function of mcp_server.py taking exactly one parameter",
            )
        info["extra"].append(name)
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
    if final.value is not None and not (
        isinstance(final.value, ast.Tuple) and all(isinstance(e, ast.Name) for e in final.value.elts)
    ):
        raise bad(final)
    del args_n
    return info


def _analyse_entry(fn: ast.FunctionDef) -> None:
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
        and not first.value.args
    ):
        raise _Reject(f"line {first.lineno}: mcp_server() does not start with get_mcp_instance()")
    banner_call = _expr_of('print("x", file=sys.stderr)')
    assert isinstance(banner_call, ast.Call)
    banner = banner_call.keywords[0]
    for stmt in body[1:-1]:
        ok = (
            isinstance(stmt, ast.Expr)
            and _is_call(stmt.value, "print")
            and len(stmt.value.keywords) == 1
            and ast.dump(stmt.value.keywords[0]) == ast.dump(banner)
        )
        if not ok:
            raise _Reject(f"line {stmt.lineno}: `{ast.unparse(stmt)[:70]}` is outside the banner/dispatch shape")
    last = body[-1]
    if len(body) < 2 or ast.dump(last) != ast.dump(ast.parse(_DISPATCH).body[0]):
        raise _Reject(f"line {last.lineno}: mcp_server() does not end with the standard transport dispatch")


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


@rule("w1.g3")
def g3(ctx: Ctx) -> None:
    path = ctx.pkg / "mcp_server.py"
    rel = ctx.rel(path)
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    tree = _parse(text)
    if tree is None:
        ctx.note("w1.g3", "mcp_server.py does not parse", rel, blocking=True)
        return
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    if "get_mcp_instance" not in funcs:
        if "mcp_server" in funcs:
            ctx.note(
                "w1.g3", "mcp_server() exists without get_mcp_instance(); not the bootstrap shape", rel, blocking=True
            )
        return
    try:
        info = _analyse_instance(funcs["get_mcp_instance"], funcs)
        if "mcp_server" in funcs:
            _analyse_entry(funcs["mcp_server"])
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
        and len(n.body) == 1
        and not n.orelse
        and isinstance(n.body[0], ast.Expr)
        and _is_call(n.body[0].value, "mcp_server")
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
    # other modules must not import the deleted functions
    for other in _py_files(ctx.pkg):
        if other == path or other.name == "__main__.py" and other.parent == ctx.pkg:
            continue
        if re.search(r"\bget_mcp_instance\b", other.read_text(encoding="utf-8")):
            ctx.note("w1.g3", "another module uses get_mcp_instance; hand-migrate", ctx.rel(other), True)
            return
    # extraction
    imports = _import_map(tree, ctx.pkg_name, f"{ctx.pkg_name}.mcp_server")
    local = _top_defs(ast.Module(body=kept, type_ignores=[]))
    own = f"{ctx.pkg_name}.mcp_server"
    import_lines: list[str] = []
    exprs: dict[str, str] = {}

    def need(node: ast.expr, what: str) -> None:
        for name in sorted(_name_loads([node])):
            if hasattr(builtins, name) and name not in imports and name not in local:
                continue
            line = _import_for(name, imports, local, own)
            if line is None:
                raise _Reject(f"{what} uses `{name}` which mcp_server.py does not define or import")
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
        exprs["api"] = surf["client_cls"].id
        exprs["get_client"] = surf["get_client"].id
        need(surf["client_cls"], "client_cls")
        need(surf["get_client"], "get_client")
        for key in _SURFACE_KWARGS:
            if key not in surf:
                continue
            node = surf[key]
            if key == "verbose_targets":
                node = ast.Tuple(elts=node.elts, ctx=ast.Load()) if isinstance(node, ast.List) else None
                exprs[key] = ast.unparse(node) if node else f"tuple({ast.unparse(surf[key])})"
                need(surf[key], key)
            else:
                exprs[key] = _src(node)
                need(node, key)
        for name in info["extra"]:
            import_lines.append(f"from {own} import {name}")
    except _Reject as err:
        ctx.note("w1.g3", f"cannot extract Connector values: {err}", rel, True)
        return
    # the surface expressions may name things this rule deletes
    deleted_names = {n.name for n in dele if isinstance(n, ast.FunctionDef)}
    if any(f"from {own} import {n}" in import_lines for n in deleted_names):
        ctx.note("w1.g3", "a Connector value names a function the bootstrap deletes", rel, True)
        return
    candidates = _name_loads(dele)
    new = _delete_spans(text, [_span(n) for n in dele])
    new = _prune_imports(new, candidates)
    ctx.write(rel, new, "w1.g3")
    ctx.options[_G3_KEY] = {
        "exprs": exprs,
        "imports": sorted(set(import_lines), key=lambda s: (s.startswith("from agent"), s)),
        "health": info["health"],
        "extra": list(info["extra"]),
    }
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
        if f"from {ctx.pkg_name} import" not in text and not _relative_init_import(ctx, f):
            continue
        tree = _parse(text)
        if tree is None:
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
        if rep:
            edits[ctx.rel(f)] = text
    return edits, bad


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
        ctx.note(
            rule_id,
            f"lazy-import scaffold kept: names with no core module owner: {bad}",
            ctx.rel(ctx.pkg / "__init__.py"),
            True,
        )
        return None
    for rel, new in edits.items():
        ctx.write(rel, new, rule_id)
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
        ctx.note(
            "w1.g4", "no `connector = Connector(...)` in the package and no bootstrap to extract it from", rel, True
        )
        return
    text = init.read_text(encoding="utf-8") if init.is_file() else ""
    head = _remove_scaffold(ctx, "w1.g4")
    base = head if head is not None else text
    exprs = stash["exprs"]
    pkg = ctx.pkg_name
    sdk = "from agent_connector_sdk.connector import Connector"
    lines = [sdk, "", *stash["imports"]]
    kw = [
        f"    api={exprs['api']},",
        f"    get_client={exprs['get_client']},",
        f'    tools="{pkg}.mcp_server",',
        f"    instructions={exprs['instructions']},",
    ]
    kw += [f"    {k}={exprs[k]}," for k in _SURFACE_KWARGS if k in exprs]
    extra = stash.get("extra") or []
    if extra:
        kw.append(f"    extra_registrations=({', '.join(extra)}{',' if len(extra) == 1 else ''}),")
    block = "\n".join([*lines, "", "connector = Connector(", *kw, ")"]) + "\n"
    out = (base.rstrip() + "\n\n" if base.strip() else "") + block
    ctx.write(rel, out, "w1.g4")


# --- g.5 / g.6 / g.1 / g.2 ------------------------------------------------------------------------------
_MAIN = 'from agent_connector_sdk import run\n\nif __name__ == "__main__":\n    run()\n'


@rule("w1.g5")
def g5(ctx: Ctx) -> None:
    path = ctx.pkg / "__main__.py"
    if not path.is_file() or path.read_text(encoding="utf-8") == _MAIN:
        return
    mcp = ctx.pkg / "mcp_server.py"
    if mcp.is_file() and "def get_mcp_instance" in mcp.read_text(encoding="utf-8"):
        return  # bootstrap kept, __main__ still valid
    tree = _parse(path.read_text(encoding="utf-8"))
    ok = tree is not None and len(tree.body) == 2
    if tree is not None and ok:
        imp, main = tree.body
        ok = (
            isinstance(imp, ast.ImportFrom)
            and imp.module == f"{ctx.pkg_name}.mcp_server"
            and [a.name for a in imp.names] == ["mcp_server"]
            and isinstance(main, ast.If)
            and ast.dump(main.test) == ast.dump(_expr_of('__name__ == "__main__"'))
            and len(main.body) == 1
            and isinstance(main.body[0], ast.Expr)
            and _is_call(main.body[0].value, "mcp_server")
            and not main.body[0].value.args
            and not main.orelse
        )
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
        if value not in (f"{ctx.pkg_name}.mcp_server:mcp_server", f"{ctx.pkg_name}.__main__:main"):
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
    if not isinstance(n.test, ast.Compare) or len(n.test.ops) != 1 or not _is_version_ref(n.test.left):
        return False
    op, right = n.test.ops[0], n.test.comparators[0]
    return isinstance(op, ast.Eq) or (
        isinstance(op, ast.IsNot) and isinstance(right, ast.Constant) and right.value is None
    )


def _clean_version_asserts(text: str) -> str:
    tree = _parse(text)
    if tree is None or "__version__" not in text:
        return text
    spans: list[tuple[int, int]] = []
    candidates: set[str] = set()
    parents: list[ast.AST] = [tree]
    for parent in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(parent, field, None)
            if not isinstance(stmts, list) or not stmts or not isinstance(stmts[0], ast.stmt):
                continue
            hits = [s for s in stmts if _is_version_assert(s)]
            if not hits:
                continue
            rest = [s for s in stmts if s not in hits and not _doc(s)]
            if not rest and isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef) and field == "body":
                spans.append(_span(parent))
                candidates |= _name_loads([parent])
            elif not rest and not isinstance(parent, ast.Module):
                continue  # block would be empty: leave for review through the remaining reference scan
            else:
                for h in hits:
                    spans.append(_span(h))
                    candidates |= _name_loads([h])
    del parents
    # drop spans nested in another span
    spans = [s for s in spans if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in spans)]
    if not spans:
        return text
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
        for tf in _py_files(ctx.root):
            if "tests" in tf.relative_to(ctx.root).parts or tf.name.startswith("test_"):
                tt = tf.read_text(encoding="utf-8")
                cleaned = _clean_version_asserts(tt)
                if cleaned != tt:
                    ctx.write(ctx.rel(tf), cleaned, "w1.k4")
        rest = [n for n in tree.body if n not in hits]
        if "__version__" in _name_loads(rest):
            ctx.note("w1.k1", "`__version__` is still read inside the module; rewrite that use by hand", rel, True)
            continue
        importers = _version_importers(ctx, mod)
        blocked = False
        rewrites: list[tuple[Path, ast.ImportFrom]] = []
        for imp_file, node in importers:
            is_test = "tests" in imp_file.relative_to(ctx.root).parts or imp_file.name.startswith("test_")
            if is_test or [a.name for a in node.names] != ["__version__"] or node.names[0].asname:
                ctx.note("w1.k1", f"`__version__` of {mod} is imported here; rewrite by hand", ctx.rel(imp_file), True)
                blocked = True
            else:
                rewrites.append((imp_file, node))
        attr = re.compile(rf"\b{re.escape(mod)}\.__version__")
        for tf in _py_files(ctx.root):
            if tf != f and attr.search(tf.read_text(encoding="utf-8")):
                ctx.note("w1.k1", f"`{mod}.__version__` is read here; rewrite by hand", ctx.rel(tf), True)
                blocked = True
        if blocked:
            continue
        for imp_file, node in rewrites:
            t = imp_file.read_text(encoding="utf-8")
            new = f'from importlib.metadata import version as _v\n\n__version__ = _v("{ctx.dist}")'
            ctx.write(ctx.rel(imp_file), _replace_span(t, node.lineno, node.end_lineno or node.lineno, new), "w1.k1")
        new_text = _delete_spans(text, [_span(n) for n in hits])
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


@rule("w1.k4")
def k4(ctx: Ctx) -> None:
    for f in _py_files(ctx.root):
        parts = f.relative_to(ctx.root).parts
        if "tests" not in parts and not f.name.startswith("test_"):
            continue
        old = f.read_text(encoding="utf-8")
        new = _clean_version_asserts(old)
        if new != old:
            ctx.write(ctx.rel(f), new, "w1.k4")


# --- i: connector_sources becomes data only -------------------------------------------------------------
def _canonical_declaration() -> str:
    return ast.dump(ast.parse(_DECLARATION).body[0])


def _declaration_equal(node: ast.FunctionDef) -> bool:
    return ast.dump(node) == _canonical_declaration()


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
        first = True
        for start, end, repl in sorted(import_edits, key=lambda e: -e[0]):
            lines2 = text2.split("\n")
            del lines2[start - 1 : end]
            text2 = "\n".join(lines2)
        # re-insert: after the last future/top import line -> at the original first import location
        if adds:
            ins = min((e[0] for e in import_edits), default=None)
            keep_lines = [e[2] for e in import_edits if e[2]]
            block = "\n".join([*adds, *keep_lines])
            lines2 = text2.split("\n")
            at = (ins - 1) if ins else _first_import_line(tree)
            lines2[at:at] = block.split("\n")
            text2 = "\n".join(lines2)
        elif import_edits:
            lines2 = text2.split("\n")
            at = min(e[0] for e in import_edits) - 1
            lines2[at:at] = [e[2] for e in import_edits if e[2]]
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
        ctx.note("w1.i1", "declaration() is not the standard 18-line body; hand-migrate to load_declaration", rel, True)
        return
    edits, bad = _rewrite_declaration_users(ctx)
    if bad:
        ctx.note("w1.i1", f"declaration()/CONNECTOR is used in a form the rule cannot rewrite: {bad}", rel, True)
        return
    for erel, etext in edits.items():
        ctx.write(erel, etext, "w1.i1")
    new = _delete_spans(text, [_span(decl[0])])
    cand = {"IngestSourceDeclaration", "IngestSourceSpec"}
    new_tree = _parse(new)
    if new_tree is not None:
        consts = [
            n
            for n in new_tree.body
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and ast.unparse(n.targets[0]) == "CONNECTOR"
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
        (n for n in tree.body if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "SCHEMA_MAPPINGS"), None
    )
    if node is None:
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
    block = f"SCHEMA_VERSION = 2\n\nFIELD_SETS = {_emit(field_sets, 0)}\n\nSCHEMA_MAPPINGS = {_emit(out, 0)}"
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
    extras = sorted({e.strip() for e in (m.group(2) or "").split(",") if e.strip()} | {"mcp"})
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
        opt = data.get("project", {}).get("optional-dependencies", {})
        drop = [
            k
            for k in ("mcp", "all")
            if k in opt and len(opt[k]) == 1 and opt[k][0].replace(" ", "").startswith("agent-connector-sdk")
        ]
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


# --- g.7 tests importing the deleted functions ------------------------------------------------------------
def _deleted_symbol_users_in(ctx: Ctx, text: str) -> list[str]:
    tree = _parse(text)
    if tree is None:
        return []
    hits = []
    mod = f"{ctx.pkg_name}.mcp_server"
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module in (mod, ctx.pkg_name):
            hits += [a.name for a in n.names if a.name in ("get_mcp_instance", "mcp_server")]
            if n.module == mod:
                hits += [a.name for a in n.names if a.name == "__version__"]
    if re.search(r"\bget_mcp_instance\b", text) and "get_mcp_instance" not in hits:
        hits.append("get_mcp_instance")
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


def _splice(text: str, node: ast.stmt, new: str) -> str:
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


def _rewrite_server_test(ctx: Ctx, text: str) -> tuple[str | None, list[str]]:
    """Rewrite the ``get_mcp_instance()`` unpack form to ``build_server``; (new text | None, blocking reasons)."""
    tree = _parse(text)
    if tree is None:
        return None, []
    mod = f"{ctx.pkg_name}.mcp_server"
    parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    edits: list[tuple[ast.stmt, str]] = []
    problems: list[str] = []
    handled: set[ast.AST] = set()
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
        elif isinstance(n, ast.Assign) and _is_call(n.value, "get_mcp_instance"):
            handled.add(n.value.func)
            if n.value.args or n.value.keywords or len(n.targets) != 1:
                problems.append(f"line {n.lineno}: calls get_mcp_instance with arguments")
                continue
            tgt, why = _build_server_targets(n.targets[0], _scope_of(n, parents, tree))
            if tgt is None:
                problems.append(f"line {n.lineno}: {why}")
                continue
            edits.append((n, f'{tgt} = build_server("{ctx.pkg_name}", command_args=[])'))
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
