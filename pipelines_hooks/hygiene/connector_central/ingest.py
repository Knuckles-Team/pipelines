"""Ingest rules i1-i9: ``<pkg>/kg_ingest.py`` plumbing becomes one ``STREAM`` (PIPE-GATES-R016.82-.90).

SDK 0.5.2 ``SourceStream`` replaces the duplicated ``_BINDING`` / ``_to_entity`` / ``_to_relationship`` /
``ingest_entities`` / ``ingest_documents`` block every connector carries. The rewrite is all or nothing per repo:
``ingest.i1`` analyses the whole repo up front (the standard functions by normalised AST, the binding, every call
site and import in the package and its tests) and plans three stages; i1 deletes the plumbing, i2 writes ``STREAM``
and fixes the SDK import, i3 rewrites the call sites and deletes tests of the removed private helpers. When anything
is off the repo gets one review item and no file changes, so a connector is never left half-migrated.

Rules i7, i8 and i9 detect shapes the mechanical rewrite does not cover (paging and clients in the ingest module,
best-effort wrappers and second bindings, media or mixed change sets) and record review items; they run first and
their shapes also stop i1. i4 and i5 (dispatch tables, ``RecordMap``) are detect-and-note. i6 replaces a local
``_records`` / ``_ext_id`` / ``_slug`` only when it is AST-equal to the SDK helper. A repo with no ``kg_ingest.py``
is a silent no-op for every rule.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import io
import re
import tokenize
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .base import Ctx, rule

ORDER: tuple[str, ...] = (
    "ingest.i7",
    "ingest.i8",
    "ingest.i9",
    "ingest.i1",
    "ingest.i2",
    "ingest.i3",
    "ingest.i4",
    "ingest.i5",
    "ingest.i6",
)

KG = "kg_ingest.py"
SDK_MOD = "agent_connector_sdk.ingest"
_PLAN_KEY = "_ingest_plan"
_STD_NAMES = {"_to_entity", "_to_relationship", "_to_document", "ingest_entities", "ingest_documents"}
_REMOVABLE_IMPORTS = {
    "ChangeSet",
    "Document",
    "Entity",
    "Relationship",
    "IngestBinding",
    "KnowledgeIngest",
    "current_ingest",
    "IngestError",
}
_MAX_LINE = 88


class _Refuse(Exception):
    """The repo does not have the exact pre-migration shape; the message is the review reason."""


# ---------------------------------------------------------------- text edits


@dataclass
class _Edits:
    """Line-block and in-line span replacements on one file, each tagged with the stage that applies it."""

    text: str
    blocks: dict[int, tuple[int, list[str] | None, int]] = field(default_factory=dict)  # first -> (last, new, stage)
    spans: list[tuple[int, int, int, str, int]] = field(default_factory=list)  # (line, c0, c1, new, stage)

    def block(self, first: int, last: int, new: list[str] | None, stage: int) -> None:
        for f, (l_, _n, _s) in self.blocks.items():
            if not (last < f or first > l_):
                raise _Refuse(f"overlapping edits at lines {first}-{last}")
        self.blocks[first] = (last, new, stage)

    def span(self, line: int, c0: int, c1: int, new: str, stage: int) -> None:
        self.spans.append((line, c0, c1, new, stage))

    def deleted_lines(self) -> set[int]:
        return {i for f, (l_, n, _s) in self.blocks.items() if n is None for i in range(f, l_ + 1)}

    def render(self, stage: int) -> str:
        lines = self.text.splitlines(keepends=True)
        out: list[tuple[str, bool]] = []  # (text, deleted)
        i = 1
        while i <= len(lines):
            blk = self.blocks.get(i)
            if blk and blk[2] <= stage:
                last, new, _s = blk
                if new is None:
                    out.extend((lines[j - 1], True) for j in range(i, last + 1))
                else:
                    out.extend((ln + "\n", False) for ln in new)
                i = last + 1
                continue
            line = lines[i - 1]
            for ln, c0, c1, text, st in sorted(self.spans, key=lambda s: -s[1]):
                if ln == i and st <= stage:
                    line = line[:c0] + text + line[c1:]
            out.append((line, False))
            i += 1
        return _collapse(out, self.text.endswith("\n"))


def _collapse(out: list[tuple[str, bool]], final_newline: bool) -> str:
    """Join lines; each run of deleted and blank lines around a deletion keeps its widest blank gap (max 2)."""
    res: list[str] = []
    i = 0
    while i < len(out):
        text, dele = out[i]
        if not dele and text.strip():
            res.append(text)
            i += 1
            continue
        j = i
        while j < len(out) and (out[j][1] or not out[j][0].strip()):
            j += 1
        run = out[i:j]
        if not any(d for _t, d in run):
            res.extend(t for t, _d in run)
        else:
            best = cur = 0
            for t, d in run:
                cur = cur + 1 if (not d and not t.strip()) else 0
                best = max(best, cur)
            gap = 0 if (i == 0 or j == len(out)) else min(best, 2)
            res.extend(["\n"] * gap)
        i = j
    text = "".join(res)
    if final_newline:
        text = text.rstrip("\n") + "\n"
    return text


def _char_col(text_lines: list[str], lineno: int, col_bytes: int) -> int:
    return len(text_lines[lineno - 1].encode("utf-8")[:col_bytes].decode("utf-8", "ignore"))


def _first_line(node: ast.stmt) -> int:
    decos = getattr(node, "decorator_list", None) or []
    return min([node.lineno, *(d.lineno for d in decos)])


# ---------------------------------------------------------------- tokens


@dataclass
class _Toks:
    names: list[tuple[int, int, str]]  # (row, col, name)
    strings: list[tuple[int, int, str]]  # (row, endrow, text)


def _tokens(text: str) -> _Toks:
    names: list[tuple[int, int, str]] = []
    strings: list[tuple[int, int, str]] = []
    str_types = {tokenize.STRING}
    for extra in ("FSTRING_MIDDLE", "TSTRING_MIDDLE"):
        if hasattr(tokenize, extra):
            str_types.add(getattr(tokenize, extra))
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.NAME:
            names.append((tok.start[0], tok.start[1], tok.string))
        elif tok.type in str_types:
            strings.append((tok.start[0], tok.end[0], tok.string))
    return _Toks(names, strings)


def _docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def _word(names: set[str]) -> re.Pattern[str]:
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names)) + r")\b")


# ---------------------------------------------------------------- normalisation


class _Norm(ast.NodeTransformer):
    def __init__(self, names: dict[str, str], consts: dict[str, tuple[str, ...]], rename_args: bool) -> None:
        self.names = dict(names)
        self.consts = consts
        self.rename_args = rename_args

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id in self.consts and isinstance(node.ctx, ast.Load):
            return ast.Tuple(elts=[ast.Constant(v) for v in self.consts[node.id]], ctx=ast.Load())
        node.id = self.names.get(node.id, node.id)
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.annotation = None
        node.arg = self.names.get(node.arg, node.arg)
        return node

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        comps = []
        for op, comp in zip(node.ops, node.comparators, strict=True):
            if isinstance(op, ast.NotIn | ast.In):
                vals = _str_set(comp)
                if vals is not None:
                    comp = ast.Tuple(elts=[ast.Constant(v) for v in vals], ctx=ast.Load())
            comps.append(comp)
        node.comparators = comps
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        last = node.values[-1]
        if isinstance(node.op, ast.Or) and isinstance(last, ast.List) and not last.elts:
            node.values[-1] = ast.Tuple(elts=[], ctx=ast.Load())
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "IngestError" and len(node.args) == 1:
            node.args = [ast.Constant("MSG")]
        return node


def _str_set(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "frozenset":
        if len(node.args) == 1 and not node.keywords:
            return _str_set(node.args[0])
        return None
    if isinstance(node, ast.Tuple | ast.Set | ast.List):
        vals = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if len(vals) == len(node.elts) and vals:
            return tuple(sorted(set(vals)))
    return None


def _norm_fn(fn: ast.AST, names: dict[str, str], consts: dict[str, tuple[str, ...]], rename_args: bool) -> str:
    fn = copy.deepcopy(fn)
    assert isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef)
    body = fn.body
    if body and isinstance(body[0], ast.Expr):
        doc = body[0].value
        if isinstance(doc, ast.Constant) and isinstance(doc.value, str):
            body = body[1:]
    fn.body = body or [ast.Pass()]
    fn.name = "FN"
    fn.returns = None
    fn.decorator_list = []
    local = dict(names)
    local.setdefault("props", "properties")
    if rename_args:
        for i, a in enumerate(fn.args.posonlyargs + fn.args.args):
            local[a.arg] = f"p{i}"
    # canonical comprehension targets, in order of appearance
    n = 0
    for node in ast.walk(fn):
        if isinstance(node, ast.comprehension):
            for t in ast.walk(node.target):
                if isinstance(t, ast.Name) and t.id not in local:
                    local[t.id] = f"c{n}"
                    n += 1
    _Norm(local, consts, rename_args).visit(fn)
    return ast.unparse(fn)


def _tmpl(src: str, rename_args: bool) -> str:
    fn = ast.parse(src).body[0]
    return _norm_fn(fn, {}, {}, rename_args)


def _helper_templates() -> dict[str, set[str]]:
    get = {"g": 'record.get("{k}")', "s": 'record["{k}"]'}
    ent: set[str] = set()
    for a in get.values():
        for b in get.values():
            for props in (True, False):
                extra = (
                    ', properties={k: v for k, v in record.items() if k not in ("id", "node_type")}' if props else ""
                )
                ent.add(
                    _tmpl(
                        f"def f(record):\n    return Entity(id={a.format(k='id')}, "
                        f"node_type={b.format(k='node_type')}{extra})",
                        True,
                    )
                )
    rel = {
        _tmpl(
            "def f(record):\n"
            "    properties = {k: v for k, v in record.items() if k not in ('source', 'target', 'relationship')}\n"
            "    return Relationship(source=record['source'], target=record['target'], "
            "relationship=record['relationship'], properties=properties or None)",
            True,
        )
    }
    doc: set[str] = set()
    for a in get.values():
        for b in get.values():
            for props in (True, False):
                extra = (
                    ', properties={k: v for k, v in record.items() if k not in ("id", "text", "title", "source_uri")}'
                    if props
                    else ""
                )
                doc.add(
                    _tmpl(
                        f"def f(record):\n    return Document(id={a.format(k='id')}, text={b.format(k='text')}, "
                        f'title=record.get("title"), source_uri=record.get("source_uri"){extra})',
                        True,
                    )
                )
    return {"to_entity": ent, "to_relationship": rel, "to_document": doc}


_SUBMIT = (
    "    service = ingest or current_ingest()\n"
    "    receipt = await service.submit(BINDING, change_set)\n"
    '    return {"nodes": receipt.affected_count, "edges": receipt.relationship_count}\n'
)


def _ingest_templates() -> dict[str, set[str]]:
    ents: set[str] = set()
    docs: set[str] = set()
    for guard in (True, False):
        g_e = "    if not entities:\n        raise IngestError(MSG)\n" if guard else ""
        g_d = "    if not documents:\n        raise IngestError(MSG)\n" if guard else ""
        ents.add(
            _tmpl(
                "async def f(entities, relationships=None, *, ingest=None):\n" + g_e + "    change_set = ChangeSet("
                "entities=tuple(TO_ENTITY(e) for e in entities), "
                "relationships=tuple(TO_RELATIONSHIP(r) for r in relationships or ()))\n" + _SUBMIT,
                False,
            )
        )
        for inner in (
            "TO_DOCUMENT(d)",
            'Document(id=d["id"], text=d["text"], title=d.get("title"), source_uri=d.get("source_uri"))',
        ):
            docs.add(
                _tmpl(
                    "async def f(documents, *, ingest=None):\n"
                    + g_d
                    + f"    change_set = ChangeSet(documents=tuple({inner} for d in documents))\n"
                    + _SUBMIT,
                    False,
                )
            )
    return {"ingest_entities": ents, "ingest_documents": docs}


_HELPERS = _helper_templates()
_INGESTS = _ingest_templates()
_TOKEN = {"to_entity": "TO_ENTITY", "to_relationship": "TO_RELATIONSHIP", "to_document": "TO_DOCUMENT"}


# ---------------------------------------------------------------- shape detection (i7 i8 i9)


def _kg(ctx: Ctx) -> tuple[str, str, ast.Module] | None:
    path = ctx.pkg / KG
    if not path.is_file():
        return None
    rel = ctx.rel(path)
    text = ctx.read(rel)
    try:
        return rel, text, ast.parse(text)
    except SyntaxError:
        return rel, text, ast.Module(body=[], type_ignores=[])


def _paging_reasons(tree: ast.Module) -> list[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            found.add("while loop")
        elif isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if "checkpoint" in name.lower():
                found.add("checkpoint")
            if name in ("get_client", "register_ingest_tools"):
                found.add(name)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == "register_ingest_tools" or "checkpoint" in node.name.lower():
                found.add(node.name)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for m in mods:
                if m.split(".")[0] in ("httpx", "requests"):
                    found.add(m.split(".")[0])
        elif isinstance(node, ast.Await):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Name | ast.Attribute):
                    name = sub.id if isinstance(sub, ast.Name) else sub.attr
                    if "client" in name.lower():
                        found.add("awaited client call")
    return sorted(found)


def _best_effort_reasons(tree: ast.Module) -> list[str]:
    found: set[str] = set()
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) == "IngestBinding"]
    if len(calls) > 1:
        found.add(f"{len(calls)} IngestBinding values (document_binding)")
    exception_names = {"IngestError", "IngestUnavailableError"}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module != "agent_connector_sdk.ingest":
            continue
        for alias in node.names:
            if alias.name in exception_names:
                exception_names.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            for sub in ast.walk(node.type):
                if isinstance(sub, ast.Name) and sub.id in exception_names:
                    found.add(f"except {sub.id} wrapper (best_effort)")
    return sorted(found)


def _change_set_reasons(tree: ast.Module) -> list[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) == "ChangeSet":
            if node.args:
                found.add("ChangeSet positional arguments")
            if any(keyword.arg is None for keyword in node.keywords):
                found.add("ChangeSet dynamic keyword arguments")
            kws = {k.arg for k in node.keywords}
            if "media" in kws:
                found.add("ChangeSet(media=...)")
            if kws & {"mode", "live_ids", "withdrawals"}:
                found.add("ChangeSet with mode/live_ids/withdrawals")
            if "documents" in kws and kws & {"entities", "relationships"}:
                found.add("mixed ChangeSet")
        elif isinstance(node, ast.Name) and node.id == "MediaAsset":
            found.add("MediaAsset")
    return sorted(found)


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _unsupported(tree: ast.Module) -> list[str]:
    return _paging_reasons(tree) + _best_effort_reasons(tree) + _change_set_reasons(tree)


def _assigned_names(node: ast.stmt) -> set[str]:
    """Return names assigned by a simple or annotated module assignment."""
    if isinstance(node, ast.Assign):
        return {target.id for target in node.targets if isinstance(target, ast.Name)}
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()


@rule("ingest.i7")
def checkpointed_paging(ctx: Ctx) -> None:
    """i7 / i11: paging, cursors and source clients inside ``kg_ingest.py`` go to review (the move is by hand)."""
    kg = _kg(ctx)
    if kg and (reasons := _paging_reasons(kg[2])):
        ctx.note("ingest.i7", "review: checkpointed paging (" + ", ".join(reasons) + ")", kg[0])


@rule("ingest.i8")
def best_effort_and_split(ctx: Ctx) -> None:
    """i8: best-effort wrappers and a second document binding are detected; the option rewrite is by hand."""
    kg = _kg(ctx)
    if kg and (reasons := _best_effort_reasons(kg[2])):
        ctx.note("ingest.i8", "best_effort/document_binding not exact: " + ", ".join(reasons), kg[0])


@rule("ingest.i9")
def media_and_mixed(ctx: Ctx) -> None:
    """i9: media and mixed change sets are detected; ``STREAM.media`` / ``STREAM.batch`` move by hand."""
    kg = _kg(ctx)
    if kg and (reasons := _change_set_reasons(kg[2])):
        ctx.note("ingest.i9", "media/mixed change set not exact: " + ", ".join(reasons), kg[0])


# ---------------------------------------------------------------- the i1-i3 plan


def _module_strs(tree: ast.Module) -> dict[str, str]:
    seen: dict[str, int] = {}
    vals: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            seen[name] = seen.get(name, 0) + 1
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                vals[name] = node.value.value
    return {k: v for k, v in vals.items() if seen[k] == 1}


def _module_sets(tree: ast.Module) -> dict[str, tuple[ast.Assign, tuple[str, ...]]]:
    out: dict[str, tuple[ast.Assign, tuple[str, ...]]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            vals = _str_set(node.value)
            if vals is not None:
                out[node.targets[0].id] = (node, vals)
    return out


def _scan_files(ctx: Ctx) -> list[str]:
    rels: list[str] = []
    for base in (ctx.pkg, ctx.root / "tests"):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            parts = set(p.relative_to(ctx.root).parts)
            if parts & {".venv", "venv", "__pycache__", "node_modules", "build", "dist"}:
                continue
            rels.append(ctx.rel(p))
    return rels


def _quote(s: str) -> str:
    return '"' + s + '"' if re.fullmatch(r"[A-Za-z0-9_.:/ -]*", s) else repr(s)


def _isort_key(name: str) -> tuple[int, str, str]:
    bare = name.lstrip("_")
    kind = 0 if bare.isupper() else 1 if bare[:1].isupper() else 2
    return (kind, name.lower(), name)


def _render_import(text_lines: list[str], node: ast.ImportFrom, names: list[str]) -> list[str] | None:
    """The import statement with ``names`` (kept order, or isort order when it was sorted); None deletes it."""
    old = [a.name for a in node.names]
    out: list[str] = []
    for n in names:
        if n not in out:
            out.append(n)
    if not out:
        return None
    if old == sorted(old, key=_isort_key):
        out.sort(key=_isort_key)
    indent = text_lines[node.lineno - 1][: _char_col(text_lines, node.lineno, node.col_offset)]
    head = f"{indent}from {'.' * node.level}{node.module or ''} import "
    one = head + ", ".join(out)
    if node.lineno == node.end_lineno and len(one) <= _MAX_LINE:
        return [one]
    return [head + "(", *(f"{indent}    {n}," for n in out), f"{indent})"]


@dataclass
class _Plan:
    files: dict[str, _Edits]
    kg_rel: str
    summary: str


def _imports_kg(ctx: Ctx, rel: str, node: ast.ImportFrom) -> bool:
    if node.level == 0:
        return node.module == f"{ctx.pkg_name}.kg_ingest"
    parts = Path(rel).parts
    if not rel.startswith(ctx.rel(ctx.pkg) + "/"):
        return False
    depth = len(parts) - len(Path(ctx.rel(ctx.pkg)).parts)  # 1 = file directly in the package
    return node.module == "kg_ingest" and node.level == depth


def _imports_kg_module(ctx: Ctx, rel: str, node: ast.ImportFrom) -> bool:
    if not any(a.name == "kg_ingest" and a.asname is None for a in node.names):
        return False
    if node.level == 0:
        return node.module == ctx.pkg_name
    depth = len(Path(rel).parts) - len(Path(ctx.rel(ctx.pkg)).parts)
    return node.module is None and node.level == depth and rel.startswith(ctx.rel(ctx.pkg) + "/")


def _build_plan(ctx: Ctx) -> _Plan | None:  # noqa: C901 - one linear preflight, every branch is a refusal
    kg = _kg(ctx)
    if kg is None:
        return None
    kg_rel, text, tree = kg
    if not tree.body:
        raise _Refuse("kg_ingest.py does not parse")
    if reasons := _unsupported(tree):
        raise _Refuse("shape handled by i7/i8/i9: " + ", ".join(reasons))
    tl = text.splitlines(keepends=True)
    strs = _module_strs(tree)
    sets = _module_sets(tree)
    consts = {k: v for k, (_n, v) in sets.items()}

    # binding
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) == "IngestBinding"]
    binds = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and isinstance(n.value, ast.Call)
        and _call_name(n.value) == "IngestBinding"
    ]
    if len(calls) != 1 or len(binds) != 1:
        raise _Refuse("expected exactly one module-level `_BINDING = IngestBinding(...)`")
    bind = binds[0]
    bcall = bind.value
    assert isinstance(bcall, ast.Call) and isinstance(bind.targets[0], ast.Name)
    bname = bind.targets[0].id
    kw = {k.arg: k.value for k in bcall.keywords}
    if bcall.args or set(kw) != {"connector", "stream"}:
        raise _Refuse("IngestBinding must take exactly connector= and stream=")
    resolved: dict[str, str] = {}
    used_consts: list[str] = []
    for key, val in kw.items():
        assert key is not None  # kw keys were checked against {"connector", "stream"} above
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            resolved[key] = val.value
        elif isinstance(val, ast.Name) and val.id in strs:
            resolved[key] = strs[val.id]
            used_consts.append(val.id)
        else:
            raise _Refuse(f"IngestBinding {key}= is not a string literal or module string constant")
    if resolved["connector"] != ctx.fleet:
        # The stream derives its connector from the SDK identity (entry-point name); the literal is dropped, not kept.
        ctx.note(
            "ingest.i2",
            f"IngestBinding connector={resolved['connector']!r} now derives from the SDK identity {ctx.fleet!r}",
            ctx.rel(ctx.pkg / "kg_ingest.py"),
        )
    stream = resolved["stream"]

    # standard functions
    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
    helpers: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for fn in defs:
        if isinstance(fn, ast.FunctionDef) and not fn.decorator_list:
            norm = _norm_fn(fn, {}, consts, True)
            for kind, forms in _HELPERS.items():
                if norm in forms:
                    if kind in helpers:
                        raise _Refuse(f"two functions match the standard {kind}")
                    helpers[kind] = fn
    names = {getattr(fn, "name", ""): _TOKEN[k] for k, fn in helpers.items()}
    names[bname] = "BINDING"
    ingests: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for fn in defs:
        if isinstance(fn, ast.AsyncFunctionDef) and not fn.decorator_list:
            norm = _norm_fn(fn, names, consts, False)
            for kind, forms in _INGESTS.items():
                if norm in forms:
                    if kind in ingests:
                        raise _Refuse(f"two functions match the standard {kind}")
                    ingests[kind] = fn
    if "ingest_entities" not in ingests:
        raise _Refuse("no function matches the standard ingest_entities body")
    matched = {id(n) for n in (*helpers.values(), *ingests.values())}
    for fn in defs:
        if fn.name in _STD_NAMES and id(fn) not in matched:
            raise _Refuse(f"`{fn.name}` has a non-standard body")
    edits = _Edits(text)
    deleted_spans: list[tuple[int, int]] = []
    for fn in (*helpers.values(), *ingests.values()):
        first, last = _first_line(fn), fn.end_lineno or fn.lineno
        edits.block(first, last, None, 1)
        deleted_spans.append((first, last))

    def outside(row: int) -> bool:
        return not any(a <= row <= b for a, b in deleted_spans)

    ktoks = _tokens(text)
    kdocs = _docstring_lines(tree)
    # reserved-key constants used only inside the deleted functions
    removed_consts: list[str] = []
    for cname, (cnode, _vals) in sets.items():
        uses = [r for r, _c, n in ktoks.names if n == cname and outside(r) and r != cnode.lineno]
        if cname in ("_ENTITY_RESERVED_KEYS", "_RELATIONSHIP_RESERVED_KEYS") and not uses:
            edits.block(cnode.lineno, cnode.end_lineno or cnode.lineno, None, 1)
            deleted_spans.append((cnode.lineno, cnode.end_lineno or cnode.lineno))
            removed_consts.append(cname)
    target = {getattr(ingests["ingest_entities"], "name", ""): "entities"}
    if "ingest_documents" in ingests:
        target[getattr(ingests["ingest_documents"], "name", "")] = "documents"
    hidden = {*(getattr(f, "name", "") for f in helpers.values()), bname, *removed_consts}
    if any(n == "STREAM" for _r, _c, n in ktoks.names):
        raise _Refuse("`STREAM` is already a name in kg_ingest.py")
    for r, _c, n in ktoks.names:
        if n in hidden and outside(r) and not (n == bname and r == bind.lineno):
            raise _Refuse(f"`{n}` is used outside the standard functions in kg_ingest.py")
    calls_kg = {
        (n.func.lineno, n.func.col_offset): n.func
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in target
    }
    for r, c, n in ktoks.names:
        if n in target and outside(r):
            func = next((f for (ln, col), f in calls_kg.items() if ln == r and _char_col(tl, ln, col) == c), None)
            if func is None:
                raise _Refuse(f"`{n}` is referenced other than by a direct call in kg_ingest.py line {r}")
            edits.span(r, c, c + len(n), f"STREAM.{target[n]}", 3)
    pat = _word(set(target) | hidden)
    for r, er, s in ktoks.strings:
        if pat.search(s) and outside(r) and r not in kdocs:
            raise _Refuse(f"kg_ingest.py names a removed function in a string at line {r}")

    # other files
    files: dict[str, _Edits] = {kg_rel: edits}
    reexported: set[str] = set()
    for rel in _scan_files(ctx):
        if rel == kg_rel:
            continue
        ftext = ctx.read(rel)
        if not pat.search(ftext):
            for m in re.finditer(r"kg_ingest import ([^\n]+)", ftext):
                reexported.update(re.findall(r"\w+", m.group(1)))
            continue
        fe = _plan_other(ctx, rel, ftext, target, hidden, pat, reexported)
        if fe is not None:
            files[rel] = fe

    # stage 2: STREAM and the SDK import
    ep = ctx.pyproject().get("project", {}).get("entry-points", {}).get("agent_connector_sdk.connector", {})
    if ep.get(ctx.fleet) == f"{ctx.pkg_name}:connector":
        args = f'__package__.split(".")[0], {_quote(stream)}'
        head = "STREAM = SourceStream.for_package("
    else:
        args = f"IngestBinding(connector={_quote(ctx.fleet)}, stream={_quote(stream)})"
        head = "STREAM = SourceStream("
    line = head + args + ")"
    edits.block(
        _first_line(bind),
        bind.end_lineno or bind.lineno,
        [line] if len(line) <= _MAX_LINE else [head, f"    {args}", ")"],
        2,
    )
    sdk_imports = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == SDK_MOD and n.level == 0]
    if len(sdk_imports) != 1:
        raise _Refuse(f"expected one module-level `from {SDK_MOD} import ...`")
    imp = sdk_imports[0]
    if any(a.asname for a in imp.names):
        raise _Refuse(f"aliased `from {SDK_MOD} import` names")
    final = ast.parse(edits.render(3))
    ftoks = _tokens(edits.render(3))
    fimp = next(n for n in final.body if isinstance(n, ast.ImportFrom) and n.module == SDK_MOD and n.level == 0)
    in_imp = range(fimp.lineno, (fimp.end_lineno or fimp.lineno) + 1)
    counts: dict[str, int] = {}
    for r, _c, n in ftoks.names:
        if r not in in_imp:
            counts[n] = counts.get(n, 0) + 1
    keep = [a.name for a in imp.names if a.name not in _REMOVABLE_IMPORTS or counts.get(a.name) or a.name in reexported]
    if "SourceStream" not in keep:
        keep.append("SourceStream")
    new_imp = _render_import(tl, imp, keep)
    assert new_imp is not None
    edits.block(imp.lineno, imp.end_lineno or imp.lineno, new_imp, 2)
    for cname in used_consts:
        cnode = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == cname)
        if counts.get(cname, 0) == 1 and cname not in reexported and _unused_elsewhere(ctx, cname, kg_rel):
            edits.block(cnode.lineno, cnode.end_lineno or cnode.lineno, None, 2)
    ingest_names = ", ".join(sorted(target))
    return _Plan(files, kg_rel, f"{ingest_names} -> STREAM ({stream})")


def _unused_elsewhere(ctx: Ctx, name: str, kg_rel: str) -> bool:
    pat = _word({name})
    return not any(pat.search(ctx.read(rel)) for rel in _scan_files(ctx) if rel != kg_rel)


def _plan_other(  # noqa: C901 - one linear site check per file
    ctx: Ctx,
    rel: str,
    text: str,
    target: dict[str, str],
    hidden: set[str],
    pat: re.Pattern[str],
    reexported: set[str],
) -> _Edits | None:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise _Refuse(f"{rel} does not parse") from exc
    tl = text.splitlines(keepends=True)
    toks = _tokens(text)
    docs = _docstring_lines(tree)
    is_test = rel.startswith("tests/")
    edits = _Edits(text)
    # tests that use a removed private helper are deleted whole
    del_spans: list[tuple[int, int]] = []
    hidden_rows = {r for r, _c, n in toks.names if n in hidden}
    kg_imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and _imports_kg(ctx, rel, n)]
    import_rows = {r for n in kg_imports for r in range(n.lineno, (n.end_lineno or n.lineno) + 1)}
    for r in sorted(hidden_rows - import_rows):
        if any(a <= r <= b for a, b in del_spans):
            continue
        owner = next(
            (
                n
                for n in tree.body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                and n.name.startswith("test")
                and _first_line(n) <= r <= (n.end_lineno or n.lineno)
            ),
            None,
        )
        if owner is None or not is_test:
            raise _Refuse(f"{rel}:{r} uses a removed kg_ingest helper outside a test function")
        del_spans.append((_first_line(owner), owner.end_lineno or owner.lineno))
    for d0, d1 in del_spans:
        edits.block(d0, d1, None, 3)

    def outside(row: int) -> bool:
        return not any(a <= row <= b for a, b in del_spans)

    for r, _e, s in toks.strings:
        if pat.search(s) and outside(r) and r not in docs:
            raise _Refuse(f"{rel}:{r} names a removed kg_ingest function in a string")
    imported = {a.name for n in kg_imports for a in n.names}
    reexported.update(imported - set(target) - hidden)
    for n in kg_imports:
        for a in n.names:
            if a.name in set(target) | hidden and a.asname:
                raise _Refuse(f"{rel}:{n.lineno} imports `{a.name}` under an alias")
    mod_alias = any(isinstance(n, ast.ImportFrom) and _imports_kg_module(ctx, rel, n) for n in ast.walk(tree))
    sites: dict[tuple[int, int], tuple[int, str]] = {}  # (row, col) -> (len, replacement)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name) and f.id in target and f.id in imported:
            sites[(f.lineno, _char_col(tl, f.lineno, f.col_offset))] = (len(f.id), f"STREAM.{target[f.id]}")
        elif (
            isinstance(f, ast.Attribute)
            and f.attr in target
            and isinstance(f.value, ast.Name)
            and f.value.id == "kg_ingest"
            and mod_alias
            and f.end_lineno is not None
            and f.end_col_offset is not None
        ):
            end = _char_col(tl, f.end_lineno, f.end_col_offset)
            sites[(f.end_lineno, end - len(f.attr))] = (len(f.attr), f"STREAM.{target[f.attr]}")
    live_calls = 0
    for r, c, nm in toks.names:
        if nm == "STREAM" and outside(r):
            raise _Refuse(f"{rel}:{r} already uses the name `STREAM`")
        if nm not in target or not outside(r) or r in import_rows:
            continue
        if (r, c) not in sites:
            raise _Refuse(f"{rel}:{r} references `{nm}` other than by a direct call")
        ln, repl = sites[(r, c)]
        edits.span(r, c, c + ln, repl, 3)
        live_calls += 1 if nm in imported else 0
    # imports from kg_ingest; other names used only by the deleted tests
    dead = _dead_names(tree, toks, del_spans)
    for n in kg_imports:
        if not any(a.name in set(target) | hidden or a.name in dead for a in n.names):
            continue
        new: list[str] = []
        for a in n.names:
            if a.name in hidden or a.name in dead:
                continue
            if a.name in target:
                if live_calls:
                    new.append("STREAM")
                continue
            new.append(a.name)
        edits.block(n.lineno, n.end_lineno or n.lineno, _render_import(tl, n, new), 3)
    for top in tree.body:
        if isinstance(top, ast.ImportFrom) and top not in kg_imports and any(a.name in dead for a in top.names):
            if any(a.asname for a in top.names):
                continue
            keep = [a.name for a in top.names if a.name not in dead]
            edits.block(top.lineno, top.end_lineno or top.lineno, _render_import(tl, top, keep), 3)
    if not edits.blocks and not edits.spans:
        return None
    return edits


def _dead_names(tree: ast.Module, toks: _Toks, del_spans: list[tuple[int, int]]) -> set[str]:
    """Names imported at module level whose every use sits inside a deleted test."""
    if not del_spans:
        return set()
    imp_rows: set[int] = set()
    names: set[str] = set()
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and n.module != "__future__":
            imp_rows.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
            names.update(a.name for a in n.names if not a.asname)
    inside: dict[str, int] = {}
    out: dict[str, int] = {}
    for r, _c, nm in toks.names:
        if nm not in names or r in imp_rows:
            continue
        bucket = inside if any(a <= r <= b for a, b in del_spans) else out
        bucket[nm] = bucket.get(nm, 0) + 1
    return {nm for nm in inside if not out.get(nm)}


def _plan(ctx: Ctx) -> _Plan | None:
    if _PLAN_KEY in ctx.options:
        return ctx.options[_PLAN_KEY]
    plan: _Plan | None = None
    kg_path = ctx.pkg / KG
    try:
        plan = _build_plan(ctx)
    except _Refuse as exc:
        text = kg_path.read_text(encoding="utf-8") if kg_path.is_file() else ""
        migrated = "SourceStream" in text and not re.search(r"\b(_to_entity|ingest_entities|IngestBinding\()", text)
        if not migrated:
            ctx.note("ingest.i1", f"not migrated (connector unchanged): {exc}", ctx.rel(kg_path))
    except (OSError, SyntaxError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        ctx.note("ingest.i1", f"not migrated: {exc}", ctx.rel(kg_path) if kg_path.exists() else "")
    ctx.options[_PLAN_KEY] = plan
    return plan


def _apply(ctx: Ctx, stage: int, rule_id: str) -> None:
    plan = _plan(ctx)
    if plan is None:
        return
    for rel, edits in plan.files.items():
        if rel != plan.kg_rel and stage < 3:
            continue
        ctx.write(rel, edits.render(stage), rule_id)


@rule("ingest.i1")
def remove_plumbing(ctx: Ctx) -> None:
    """i1: preflight the whole repo, then delete the standard helpers and ingest functions."""
    _apply(ctx, 1, "ingest.i1")


@rule("ingest.i2")
def add_stream(ctx: Ctx) -> None:
    """i2: ``STREAM = SourceStream...`` where ``_BINDING`` stood; the SDK import names only what is still used."""
    _apply(ctx, 2, "ingest.i2")


@rule("ingest.i3")
def rewrite_call_sites(ctx: Ctx) -> None:
    """i3: call sites and imports use ``STREAM``; tests of the removed private helpers are deleted."""
    _apply(ctx, 3, "ingest.i3")
    ctx.options.pop(_PLAN_KEY, None)


# ---------------------------------------------------------------- i4 i5 (detect and note)


@rule("ingest.i4")
def dispatch_tables(ctx: Ctx) -> None:
    """i4: ``_MAPPERS`` / ``ingest_records`` dispatch moves to ``SourceStream(mappers)`` only with ``RecordMap``s."""
    kg = _kg(ctx)
    if kg is None:
        return
    rel, _text, tree = kg
    has_table = any("_MAPPERS" in _assigned_names(n) for n in tree.body)
    has_fn = any(
        isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name == "ingest_records" for n in tree.body
    )
    if has_table or has_fn:
        ctx.note("ingest.i4", "dispatch: mappers are functions, not RecordMap; table and ingest_records stay", rel)


@rule("ingest.i5")
def record_maps(ctx: Ctx) -> None:
    """i5: ``map_<kind>`` functions are listed for a by-hand ``RecordMap`` conversion; they stay valid as functions."""
    kg = _kg(ctx)
    if kg is None:
        return
    rel, _text, tree = kg
    maps = [
        n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("map_")
    ]
    if maps:
        ctx.note("ingest.i5", "RecordMap conversion not automated; mappers stay functions: " + ", ".join(maps), rel)


# ---------------------------------------------------------------- i6 helpers equal to the SDK


_SDK_HELPERS = {"_records": "records_of", "_ext_id": "ext_id", "_slug": "slug"}


def _sdk_helper_norms(ctx: Ctx) -> dict[str, str]:
    path: Path | None = None
    sdk = ctx.options.get("sdk_path")
    if sdk:
        for cand in (Path(sdk) / "agent_connector_sdk/ingest/mapping.py", Path(sdk) / "ingest/mapping.py"):
            if cand.is_file():
                path = cand
    if path is None:
        try:
            spec = importlib.util.find_spec("agent_connector_sdk.ingest.mapping")
        except (ImportError, ValueError):
            spec = None
        if spec and spec.origin:
            path = Path(spec.origin)
    if path is None or not path.is_file():
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        n.name: _norm_helper(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in _SDK_HELPERS.values()
    }


def _norm_helper(fn: ast.FunctionDef) -> str:
    fn = copy.deepcopy(fn)
    names: dict[str, str] = {}
    args = fn.args
    for i, a in enumerate([*args.posonlyargs, *args.args, *([args.vararg] if args.vararg else []), *args.kwonlyargs]):
        names[a.arg] = f"a{i}"
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id not in names:
            names[node.id] = f"v{len(names)}"
    return _norm_fn(fn, names, {}, False)


@rule("ingest.i6")
def sdk_helpers(ctx: Ctx) -> None:
    """i6: a local ``_records`` / ``_ext_id`` / ``_slug`` AST-equal to the SDK helper becomes its import."""
    kg = _kg(ctx)
    if kg is None:
        return
    rel, text, tree = kg
    local = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in _SDK_HELPERS]
    if not local:
        return
    norms = _sdk_helper_norms(ctx)
    tl = text.splitlines(keepends=True)
    toks = _tokens(text)
    edits = _Edits(text)
    added: list[str] = []
    for fn in local:
        sdk_name = _SDK_HELPERS[fn.name]
        if norms.get(sdk_name) != _norm_helper(fn):
            ctx.note("ingest.i6", f"`{fn.name}` differs from the SDK `{sdk_name}`; kept", rel)
            continue
        calls = {
            (n.func.lineno, _char_col(tl, n.func.lineno, n.func.col_offset))
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == fn.name
        }
        uses = [(r, c) for r, c, n in toks.names if n == fn.name and r != fn.lineno]
        clash = any(n == sdk_name for _r, _c, n in toks.names)
        if clash or set(uses) != calls or not _unused_elsewhere(ctx, fn.name, rel):
            ctx.note("ingest.i6", f"`{fn.name}` is referenced other than by local calls; kept", rel)
            continue
        edits.block(_first_line(fn), fn.end_lineno or fn.lineno, None, 1)
        for r, c in uses:
            edits.span(r, c, c + len(fn.name), sdk_name, 1)
        added.append(sdk_name)
    if not added:
        return
    imps = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == SDK_MOD and n.level == 0]
    if len(imps) != 1:
        ctx.note("ingest.i6", f"no single `from {SDK_MOD} import`; helpers kept", rel)
        return
    imp = imps[0]
    new = _render_import(tl, imp, [a.name for a in imp.names] + added)
    try:
        edits.block(imp.lineno, imp.end_lineno or imp.lineno, new, 1)
    except _Refuse:
        ctx.note("ingest.i6", "import overlaps an edit; helpers kept", rel)
        return
    ctx.write(rel, edits.render(1), "ingest.i6")
