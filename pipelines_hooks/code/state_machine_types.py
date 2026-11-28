"""Annotation types and the package-wide index of the Python state-machine reader.

``PackageIndex`` is built once per run from every Python source the hook scans
(PIPE-GATES-R086.21). It keys each module by its path and records, per module, the
classes (their field types, container element types and method signatures), the
functions (their return types) and the imports. A reader resolves a name seen in
one module to the class or function another module defines, so a field chain, a
return annotation or a tuple unpacking crosses files. It holds strings only (no
trees), follows at most ``MAX_HOPS`` re-exports and orders every choice by path,
so a run is bounded and deterministic.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import PurePosixPath

MAPPINGS = frozenset({"dict", "Dict", "Mapping", "MutableMapping", "defaultdict", "OrderedDict"})
TUPLES = frozenset({"tuple", "Tuple"})
CONTAINERS = (
    MAPPINGS
    | TUPLES
    | frozenset(
        {
            "list",
            "List",
            "Sequence",
            "MutableSequence",
            "set",
            "Set",
            "AbstractSet",
            "MutableSet",
            "frozenset",
            "FrozenSet",
            "Iterable",
            "Collection",
            "Iterator",
            "deque",
            "Deque",
        }
    )
)
OPAQUE_TYPES = frozenset({"Any", "object", ""})
#: How many re-exports (``from .x import Y`` chains) a name is followed through.
MAX_HOPS = 6


def name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return name(node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.unparse(node) if node is not None else ""


def functions(tree: ast.Module) -> list[tuple[str | None, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found: list[tuple[str | None, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((None, node))
        elif isinstance(node, ast.ClassDef):
            found += [(node.name, s) for s in node.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return found


def _arms(node: ast.expr) -> list[ast.expr]:
    """The arms of a union annotation (``A | B``, ``Union[A, B]``, ``Optional[A]``), with ``None`` dropped."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return [*_arms(node.left), *_arms(node.right)]
    if isinstance(node, ast.Subscript) and name(node.value) in {"Union", "Optional"}:
        items = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        return [arm for item in items for arm in _arms(item)]
    if isinstance(node, ast.Constant) and node.value is None:
        return []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return _arms(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return []
    return [node]


def annotation_type(annotation: ast.expr | None, owner: str | None) -> str | None:
    """The type an annotation names: one name, or ``A|B`` for a union (PIPE-GATES-R086.23).

    A union keeps the arms that name a type and drops the arms that cannot be a
    lifecycle type (a generic such as ``list[X]``, a literal). ``Any`` or ``object`` in a
    union, or a container, gives ``None``.
    """
    if annotation is None:
        return None
    arms = _arms(annotation)
    found: list[str] = []
    for arm in arms:
        if isinstance(arm, ast.Subscript) and name(arm.value) == "Annotated":
            first = arm.slice.elts[0] if isinstance(arm.slice, ast.Tuple) and arm.slice.elts else arm.slice
            kind = annotation_type(first, owner)
        elif isinstance(arm, (ast.Name, ast.Attribute)):
            kind = owner if name(arm) == "Self" else (None if name(arm) in OPAQUE_TYPES else name(arm))
            if kind is None:
                return None
        else:
            continue
        found += (kind or "").split("|") if kind else []
    unique = list(dict.fromkeys(found))
    if len(arms) == 1 and not unique:
        return None
    return "|".join(unique) if unique else None


def _tuple_items(annotation: ast.expr | None) -> list[ast.expr] | None:
    """The item annotations of ``tuple[A, B]`` (not ``tuple[A, ...]``), or ``None``."""
    if annotation is None:
        return None
    arms = _arms(annotation)
    if len(arms) != 1 or not isinstance(arms[0], ast.Subscript) or name(arms[0].value) not in TUPLES:
        return None
    items = arms[0].slice.elts if isinstance(arms[0].slice, ast.Tuple) else [arms[0].slice]
    if any(isinstance(item, ast.Constant) and item.value is Ellipsis for item in items):
        return None
    return list(items)


def annotation_items(annotation: ast.expr | None, owner: str | None) -> tuple[str | None, ...]:
    """The element types of a fixed-length tuple annotation, in order (PIPE-GATES-R086.22)."""
    items = _tuple_items(annotation)
    return tuple(annotation_type(item, owner) for item in items) if items is not None else ()


def annotation_element(annotation: ast.expr | None, owner: str | None) -> str | None:
    """The element type of ``dict[K, V]`` (``V``), ``list[V]``, ``set[V]``, ``Sequence[V]`` and ``tuple[V, ...]``."""
    if annotation is None:
        return None
    arms = _arms(annotation)
    if len(arms) != 1 or not isinstance(arms[0], ast.Subscript):
        return None
    annotation = arms[0]
    container = name(annotation.value)
    if container not in CONTAINERS:
        return None
    items = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
    if not items:
        return None
    if container in TUPLES and _tuple_items(annotation) is not None:
        kinds = {annotation_type(item, owner) for item in items}
        return kinds.pop() if len(kinds) == 1 else None
    return annotation_type(items[-1] if container in MAPPINGS else items[0], owner)


@dataclass(frozen=True)
class Signature:
    """What a callee's return annotation says: a type, a container element type, or tuple items."""

    returns: str | None = None
    element: str | None = None
    items: tuple[str | None, ...] = ()


def signature(function: ast.FunctionDef | ast.AsyncFunctionDef, owner: str | None) -> Signature:
    return Signature(
        annotation_type(function.returns, owner),
        annotation_element(function.returns, owner),
        annotation_items(function.returns, owner),
    )


@dataclass
class ClassInfo:
    """One class: its module path, field types, container element types and method signatures."""

    module: str
    name: str
    fields: dict[str, str] = field(default_factory=dict)
    elements: dict[str, str] = field(default_factory=dict)
    methods: dict[str, Signature] = field(default_factory=dict)


def _class_info(module: str, node: ast.ClassDef) -> ClassInfo:
    info = ClassInfo(module, node.name)
    for stmt in ast.walk(node):
        if not isinstance(stmt, ast.AnnAssign):
            continue
        target = stmt.target
        if isinstance(target, ast.Name) and stmt in node.body:
            key = target.id
        elif isinstance(target, ast.Attribute) and name(target.value) == "self":
            key = target.attr
        else:
            continue
        kind = annotation_type(stmt.annotation, node.name)
        if kind:
            info.fields.setdefault(key, kind)
        element = annotation_element(stmt.annotation, node.name)
        if element:
            info.elements.setdefault(key, element)
    for stmt in node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.methods[stmt.name] = signature(stmt, node.name)
            _assigned_fields(info, stmt)
    return info


def _assigned_fields(info: ClassInfo, method: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
    """``self.x = param`` takes the annotation of the parameter, and ``self.x = Type(..)`` the type built (PIPE-GATES-R086.21)."""
    args = [*method.args.posonlyargs, *method.args.args, *method.args.kwonlyargs]
    params = {arg.arg: arg.annotation for arg in args if arg.annotation is not None}
    for stmt in ast.walk(method):
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1):
            continue
        target, value = stmt.targets[0], stmt.value
        if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"):
            continue
        if isinstance(value, ast.Name) and value.id in params:
            kind = annotation_type(params[value.id], info.name)
            element = annotation_element(params[value.id], info.name)
        elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id[:1].isupper():
            kind, element = value.func.id, None
        else:
            continue
        if kind:
            info.fields.setdefault(target.attr, kind)
        if element:
            info.elements.setdefault(target.attr, element)


@dataclass
class ModuleInfo:
    """One module: its dotted name, classes, functions and imports."""

    path: str
    dotted: str
    package: str
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    functions: dict[str, Signature] = field(default_factory=dict)
    #: local name -> (dotted module, name in that module) for ``from m import n as local``.
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)
    #: local name -> dotted module for ``import m as local``.
    module_aliases: dict[str, str] = field(default_factory=dict)


def _statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """The top-level statements, including those under ``if TYPE_CHECKING``, ``try`` and ``with``."""
    for stmt in body:
        yield stmt
        if isinstance(stmt, ast.If):
            yield from _statements([*stmt.body, *stmt.orelse])
        elif isinstance(stmt, ast.Try):
            yield from _statements(
                [*stmt.body, *stmt.orelse, *stmt.finalbody, *(s for h in stmt.handlers for s in h.body)]
            )
        elif isinstance(stmt, ast.With):
            yield from _statements(stmt.body)


def _dotted(path: str, paths: frozenset[str]) -> tuple[str, str]:
    """``(dotted module, its package)`` of a path: the ``__init__.py`` chain names the package."""
    pure = PurePosixPath(path)
    parts = [] if pure.stem == "__init__" else [pure.stem]
    directory = pure.parent
    while str(directory) != "." and f"{directory}/__init__.py" in paths:
        parts.insert(0, directory.name)
        directory = directory.parent
    dotted = ".".join(parts)
    package = dotted if pure.stem == "__init__" else dotted.rpartition(".")[0]
    return dotted, package


def _module_info(path: str, tree: ast.Module, paths: frozenset[str]) -> ModuleInfo:
    dotted, package = _dotted(path, paths)
    module = ModuleInfo(path, dotted, package)
    for stmt in _statements(tree.body):
        if isinstance(stmt, ast.ClassDef):
            module.classes[stmt.name] = _class_info(path, stmt)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module.functions[stmt.name] = signature(stmt, None)
    _imports(module, tree)
    return module


def _imports(module: ModuleInfo, tree: ast.Module) -> None:
    """Every import of the module, in functions too; a local name imported from two places is ambiguous and dropped."""
    seen: dict[str, tuple[str, str]] = {}
    clashes: set[str] = set()
    for stmt in ast.walk(tree):
        if isinstance(stmt, ast.ImportFrom):
            base = _import_base(stmt, module.package)
            pairs = [
                (alias.asname or alias.name, (base, alias.name))
                for alias in stmt.names
                if alias.name != "*" and base is not None
            ]
        elif isinstance(stmt, ast.Import):
            pairs = [(alias.asname, (alias.name, "")) for alias in stmt.names if alias.asname]
        else:
            continue
        for local, target in pairs:
            if seen.setdefault(local, target) != target:
                clashes.add(local)
    for local, (base, original) in seen.items():
        if local in clashes:
            continue
        if original:
            module.imports[local] = (base, original)
        else:
            module.module_aliases[local] = base


def _import_base(stmt: ast.ImportFrom, package: str) -> str | None:
    """The dotted module a ``from`` import reads, with a relative level resolved against ``package``."""
    if stmt.level == 0:
        return stmt.module or None
    parts = package.split(".") if package else []
    if stmt.level - 1 > len(parts):
        return None
    base = parts[: len(parts) - (stmt.level - 1)]
    return ".".join([*base, *([stmt.module] if stmt.module else [])])


class PackageIndex:
    """Every scanned Python module, keyed by path, with name resolution across them."""

    def __init__(self, trees: dict[str, ast.Module]) -> None:
        paths = frozenset(trees)
        self.modules: dict[str, ModuleInfo] = {path: _module_info(path, trees[path], paths) for path in sorted(trees)}
        self._by_dotted: dict[str, ModuleInfo] = {}
        self._by_suffix: dict[str, list[ModuleInfo]] = {}
        for module in self.modules.values():
            self._by_dotted.setdefault(module.dotted, module)
            pure = PurePosixPath(module.path)
            parts = [part for part in (*pure.parent.parts, pure.stem) if part not in {".", "__init__"}]
            for start in range(len(parts)):
                self._by_suffix.setdefault(".".join(parts[start:]), []).append(module)

    def module(self, dotted: str) -> ModuleInfo | None:
        """The module of a dotted name: an exact match, or the one module whose path ends with it."""
        if not dotted:
            return None
        if dotted in self._by_dotted:
            return self._by_dotted[dotted]
        matches = self._by_suffix.get(dotted, [])
        return matches[0] if len(matches) == 1 else None

    def resolve(self, module_path: str, local: str) -> tuple[ModuleInfo, str] | None:
        """The module that defines ``local`` as ``module_path`` sees it, and the name it has there."""
        module = self.modules.get(module_path)
        for _ in range(MAX_HOPS + 1):
            if module is None:
                return None
            if local in module.classes or local in module.functions:
                return module, local
            imported = module.imports.get(local)
            if imported is None:
                return None
            module, local = self.module(imported[0]), imported[1]
        return None

    def module_named(self, module_path: str, local: str) -> ModuleInfo | None:
        """The module a local name stands for (``import m as local`` or ``from pkg import m as local``)."""
        module = self.modules.get(module_path)
        if module is None:
            return None
        if local in module.module_aliases:
            return self.module(module.module_aliases[local])
        imported = module.imports.get(local)
        return self.module(f"{imported[0]}.{imported[1]}") if imported else None
