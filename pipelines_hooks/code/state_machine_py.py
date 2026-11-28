"""The Python reader of the state-machine hooks: ``read_python(path, tree)``.

Built on the ``ast`` module. Every class with a status field or a lifecycle
flag becomes one ``Machine``. A receiver resolves to a type through ``self``,
annotations, constructors, copies and return types (``_Resolver``); a use counts
only against the type it resolves to. ``loose_sites`` hands the non-``self``
uses to the hook for the types of other files; a receiver that does not
resolve is reported once as ``<unresolved>``. Test files are skipped.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import NamedTuple

from pipelines_hooks.code.state_machine_types import (
    ClassInfo,
    PackageIndex,
    Signature,
    annotation_element,
    annotation_type,
    functions,
    name as _name,
)
from pipelines_hooks.code.state_machine_model import (
    LIFECYCLE_TIMESTAMPS,
    STATUS_FIELDS,
    Edge,
    Machine,
    Site,
    Use,
    attach,
)

TABLE_NAMES = frozenset({"LEGAL", "TRANSITIONS", "EDGES", "edges"})
FUNCTION_NAMES = frozenset({"transition", "apply", "step"})
STRING_TYPES = frozenset({"str", "int", "Literal"})
ENUM_BASES = frozenset({"Enum", "StrEnum", "IntEnum", "Flag", "IntFlag"})
ENUM_SUFFIXES = ("Status", "State", "Phase", "Stage", "Lifecycle")


def is_test_file(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1] if parts else ""
    return "tests" in parts[:-1] or name.startswith("test_") or name == "conftest.py"


def read_python(path: str, tree: ast.Module, index: PackageIndex | None = None) -> list[Machine]:
    """One ``Machine`` per class with a status field or lifecycle flag.

    ``index`` is the package-wide class index (``PackageIndex``) of the run; without it the
    reader knows only the classes of this one module.
    """
    if is_test_file(path):
        return []
    enums = _enum_members(tree)
    context = _Context(enums, _aliases(tree.body, enums), _imported(tree))
    module_tables = _tables(tree.body, context)
    machines = [
        machine
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name not in enums
        for machine in [_machine(path, node, context, (tree.body, module_tables), _constants(tree.body))]
        if machine is not None
    ]
    for use in _uses(path, tree, index):
        for machine in machines:
            if use.kind != "flag" and use.field == machine.status_field and use.receiver == machine.type_name:
                attach(machine, use)
    return machines


def enum_names(tree: ast.Module) -> frozenset[str]:
    """The enums and literal unions a module declares: the types that may be a state type."""
    return frozenset(_enum_members(tree))


def enum_declarations(path: str, tree: ast.Module) -> dict[str, Machine]:
    """State enum -> a declaration-only ``Machine`` for each enum an edge table of this module is written over.

    A table is recognised by its shape (``_edge_table``), under any name. The hook
    copies the declaration onto every type, in any module, that holds the enum as
    its status.
    """
    if is_test_file(path):
        return {}
    enums = _enum_members(tree)
    context = _Context(enums, _aliases(tree.body, enums), _imported(tree))
    found: dict[str, Machine] = {}
    for table, edges, enum in _tables(tree.body, context):
        if enum is None:
            continue
        machine = Machine("python", path, 0, enum, status_field="", status_type=enum, status_kind="enum")
        machine.table, machine.edges = table, edges
        _declare(machine, tree.body, enums.get(enum, ()))
        found.setdefault(enum, machine)
    return found


def _declare(machine: Machine, body: list[ast.stmt], states: tuple[str, ...]) -> None:
    function = _transition(body, None, machine.table)
    if function is not None:
        machine.function, machine.refusal = function
    machine.states = states or _edge_states(machine.edges)
    machine.initial, machine.terminals = _constants(body)


def loose_sites(path: str, tree: ast.Module, index: PackageIndex | None = None) -> list[Use]:
    """The uses whose receiver is not ``self``, and every flag use: the hook matches them by resolved type, package-wide."""
    return [] if is_test_file(path) else [use for use in _uses(path, tree, index) if not use.local]


def _enum_members(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        alias = _literal_alias(node)
        if alias is not None:
            found[alias[0]] = alias[1]
        if isinstance(node, ast.ClassDef) and any(_name(base) in ENUM_BASES for base in node.bases):
            found[node.name] = tuple(
                target.id
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                for target in stmt.targets
                if isinstance(target, ast.Name)
            )
    return found


def _literal_alias(node: ast.stmt) -> tuple[str, tuple[str, ...]] | None:
    """``Status = Literal["a", "b"]`` (or ``type Status = Literal[...]``): a literal union is a state type."""
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        name, value = node.targets[0].id, node.value
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
        name, value = node.target.id, node.value
    elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
        name, value = node.name.id, node.value
    else:
        return None
    if not (isinstance(value, ast.Subscript) and _name(value.value) == "Literal"):
        return None
    items = value.slice.elts if isinstance(value.slice, ast.Tuple) else [value.slice]
    return name, tuple(str(item.value) for item in items if isinstance(item, ast.Constant))


class _Context:
    """What a module says about its enums: their members, the aliases of them, the names it imports."""

    def __init__(self, enums: dict[str, tuple[str, ...]], aliases: dict[str, str], imported: frozenset[str]) -> None:
        self.enums, self.aliases, self.imported = enums, aliases, imported


def _aliases(body: list[ast.stmt], enums: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """``S = State`` and ``_S, _E = State, Event``: a short name for an enum."""
    found: dict[str, str] = {}
    for stmt in body:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1):
            continue
        target, value = stmt.targets[0], stmt.value
        pairs = (
            list(zip(target.elts, value.elts, strict=False))
            if isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple)
            else [(target, value)]
        )
        found |= {t.id: v.id for t, v in pairs if isinstance(t, ast.Name) and isinstance(v, ast.Name)}
    return {alias: enum for alias, enum in found.items() if enum in enums}


def _imported(tree: ast.Module) -> frozenset[str]:
    return frozenset(
        alias.asname or alias.name for node in tree.body if isinstance(node, ast.ImportFrom) for alias in node.names
    )


def _strip_optional(node: ast.expr) -> tuple[ast.expr, bool]:
    """The annotation without ``Optional[...]`` or ``| None``, and whether it was nullable."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        sides = [
            side for side in (node.left, node.right) if not (isinstance(side, ast.Constant) and side.value is None)
        ]
        if len(sides) == 1:
            return sides[0], True
    if isinstance(node, ast.Subscript) and _name(node.value) == "Optional":
        return node.slice, True
    return node, False


def _kind(annotation: ast.expr, enums: dict[str, tuple[str, ...]]) -> tuple[str, str]:
    inner, _ = _strip_optional(annotation)
    name = _name(inner)
    if name in STRING_TYPES:
        return name, "string"
    if name in enums or name.endswith(ENUM_SUFFIXES):
        return name, "enum"
    return name, ""


def _frozen(node: ast.ClassDef) -> bool:
    """A frozen dataclass, a frozen pydantic model (``model_config`` or ``Config``) or a ``NamedTuple``."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call) and any(
            kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in decorator.keywords
        ):
            return True
    if any(_name(base) == "NamedTuple" for base in node.bases):
        return True
    for stmt in node.body:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and "model_config" in ast.unparse(stmt):
            if re.search(r"frozen\W+True", ast.unparse(stmt)):
                return True
        if isinstance(stmt, ast.ClassDef) and stmt.name == "Config":
            if any("frozen" in ast.unparse(inner) and "True" in ast.unparse(inner) for inner in stmt.body):
                return True
    return False


def _fields(node: ast.ClassDef) -> list[ast.AnnAssign]:
    return [stmt for stmt in node.body if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)]


def _flag(stmt: ast.AnnAssign) -> bool:
    name = _name(stmt.target)
    if name.startswith("is_") or name.endswith("_requested") or name == "terminal":
        return True
    return name in LIFECYCLE_TIMESTAMPS and _strip_optional(stmt.annotation)[1]


def _machine(
    path: str,
    node: ast.ClassDef,
    context: _Context,
    module: tuple[list[ast.stmt], list[tuple[str, tuple[Edge, ...], str | None]]],
    module_constants: tuple[str | None, tuple[str, ...]],
) -> Machine | None:
    enums = context.enums
    fields = _fields(node)
    status = next((stmt for stmt in fields if _name(stmt.target) in STATUS_FIELDS), None)
    flags = tuple(_name(stmt.target) for stmt in fields if _flag(stmt))
    if status is None and not flags:
        return None
    machine = Machine("python", path, node.lineno, node.name, flags=flags, frozen=_frozen(node))
    if status is not None:
        machine.status_field = _name(status.target)
        machine.status_type, machine.status_kind = _kind(status.annotation, enums)
        machine.guessed_enum = machine.status_kind == "enum" and machine.status_type not in enums
        module_body, module_tables = module
        tables = [
            table
            for table in [*_tables(node.body, context), *module_tables]
            if table[2] is None or table[2] == machine.status_type
        ]
        if tables:
            machine.table, machine.edges = tables[0][:2]
        function = _transition(node.body, node.name, machine.table) or _transition(module_body, None, machine.table)
        own = _constants(node.body)
        constants = (own[0] or module_constants[0], own[1] or module_constants[1])
        if function is not None:
            machine.function, machine.refusal = function
            machine.via_enum = bool(tables) and tables[0][2] is not None and not function[0].startswith(node.name + ".")
        machine.states = enums.get(machine.status_type or "", ()) or _edge_states(machine.edges)
        machine.initial, machine.terminals = constants
    return machine


def _constants(body: list[ast.stmt]) -> tuple[str | None, tuple[str, ...]]:
    """The ``INITIAL`` state and the ``TERMINAL``/``TERMINALS`` states declared in ``body``."""
    initial: str | None = None
    terminals: tuple[str, ...] = ()
    for stmt in body:
        target = stmt.targets[0] if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 else None
        target = stmt.target if isinstance(stmt, ast.AnnAssign) else target
        value = stmt.value if isinstance(stmt, (ast.Assign, ast.AnnAssign)) else None
        name = target.id if isinstance(target, ast.Name) else ""
        if name == "INITIAL" and value is not None:
            initial = _name(value)
        elif name in {"TERMINAL", "TERMINALS"} and value is not None:
            items = value.elts if isinstance(value, (ast.Set, ast.List, ast.Tuple)) else [value]
            terminals = tuple(_name(item) for item in items)
    return initial, terminals


def _edge_states(edges: tuple[Edge, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(state for source, _, target in edges for state in (source, target)))


def _tables(body: list[ast.stmt], context: _Context) -> list[tuple[str, tuple[Edge, ...], str | None]]:
    """``(name, edges, state enum)`` of each edge table in ``body``.

    A table is a constant named ``LEGAL``, ``TRANSITIONS``, ``EDGES`` or ``edges``, or
    any constant whose value is an edge table over an enum (``_edge_table``).
    """
    found = []
    for stmt in body:
        target = stmt.targets[0] if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 else None
        target = stmt.target if isinstance(stmt, ast.AnnAssign) else target
        value = stmt.value if isinstance(stmt, (ast.Assign, ast.AnnAssign)) else None
        if not (isinstance(target, ast.Name) and value is not None):
            continue
        annotation = stmt.annotation if isinstance(stmt, ast.AnnAssign) else None
        edges = _edges(value)
        enum = _edge_table_enum(value, annotation, context) if edges else None
        if target.id in TABLE_NAMES or enum is not None:
            found.append((target.id, edges, enum if target.id not in TABLE_NAMES or enum else None))
    return found


def _from_nodes(value: ast.expr) -> list[ast.expr]:
    """The source-state expression of each entry of an edge table."""
    if isinstance(value, ast.Call) and value.args:
        return _from_nodes(value.args[0])
    nodes: list[ast.expr] = []
    if isinstance(value, ast.Dict):
        for key in value.keys:
            if key is not None:
                nodes.append(key.elts[0] if isinstance(key, ast.Tuple) and key.elts else key)
    elif isinstance(value, (ast.Set, ast.List, ast.Tuple)):
        nodes = [item.elts[0] for item in value.elts if isinstance(item, ast.Tuple) and item.elts]
    return [node for node in nodes if node is not None]


def _edge_table_enum(value: ast.expr, annotation: ast.expr | None, context: _Context) -> str | None:
    """The state enum an edge table is written over, or ``None`` when the value is not an edge table.

    Structure, not a name: every source state is ``Enum.MEMBER`` of one enum of the
    module (or an imported type), reached directly or through an alias; or the
    annotation of a mapping names its value type, an enum of the module.
    """
    sources = _from_nodes(value)
    if not sources:
        return None
    bases = {
        context.aliases.get(node.value.id, node.value.id)
        for node in sources
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    if len(bases) == 1 and len(sources) == sum(isinstance(n, ast.Attribute) for n in sources):
        (base,) = bases
        if base in context.enums or base in context.imported:
            return base
    if isinstance(annotation, ast.Subscript) and isinstance(annotation.slice, ast.Tuple) and annotation.slice.elts:
        last = _name(annotation.slice.elts[-1])
        return last if last in context.enums else None
    return None


def _edges(value: ast.expr) -> tuple[Edge, ...]:
    """``{(from, event): to}``, ``{from: {event: to}}``, ``{from: {to, ...}}`` or a list of tuples."""
    if isinstance(value, ast.Call) and value.args:
        return _edges(value.args[0])
    edges: list[Edge] = []
    if isinstance(value, ast.Dict):
        for key, target in zip(value.keys, value.values, strict=True):
            if isinstance(key, ast.Tuple) and len(key.elts) == 2:
                edges.append((_name(key.elts[0]), _name(key.elts[1]), _name(target)))
            elif isinstance(target, ast.Dict):
                edges += [
                    (_name(key), _name(event), _name(to)) for event, to in zip(target.keys, target.values, strict=True)
                ]
            elif isinstance(target, (ast.Set, ast.List, ast.Tuple)):
                edges += [(_name(key), _name(to), _name(to)) for to in target.elts]
    elif isinstance(value, (ast.Set, ast.List, ast.Tuple)):
        for item in value.elts:
            parts = [_name(part) for part in item.elts] if isinstance(item, ast.Tuple) else []
            if len(parts) == 3:
                edges.append((parts[0], parts[1], parts[2]))
            elif len(parts) == 2:
                edges.append((parts[0], parts[1], parts[1]))
    return tuple(edges)


def _transition(body: list[ast.stmt], owner: str | None, table: str | None = None) -> tuple[str, str] | None:
    """The transition function and the refusal it raises.

    A function named ``transition``, ``apply`` or ``step`` that raises a class named ``*Refused``;
    or, for a declared ``table``, any function that reads the table and raises: the class it
    raises is the refusal, whatever it is called.
    """
    for stmt in body:
        if not (isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))):
            continue
        reads_table = table is not None and any(isinstance(n, ast.Name) and n.id == table for n in ast.walk(stmt))
        if stmt.name not in FUNCTION_NAMES and not reads_table:
            continue
        for raise_node in (n for n in ast.walk(stmt) if isinstance(n, ast.Raise) and n.exc is not None):
            refusal = _name(raise_node.exc.func if isinstance(raise_node.exc, ast.Call) else raise_node.exc)
            if refusal.endswith("Refused") or reads_table:
                return (f"{owner}.{stmt.name}" if owner else stmt.name), refusal
    return None


class _Hit(NamedTuple):
    """One status or flag use found at a node: the field, the receiver expression, the kind and the stored value."""

    field: str
    receiver: ast.expr | None
    kind: str
    value: ast.expr | None = None
    replaces: bool = False


def _flag_name(field: str) -> bool:
    """A name that may be a lifecycle flag: ``is_*``, ``*_requested``, ``terminal`` or a lifecycle timestamp."""
    return (
        field.startswith("is_") or field.endswith("_requested") or field == "terminal" or field in LIFECYCLE_TIMESTAMPS
    )


def _field_kind(field: str) -> str | None:
    """``assign`` for a status field, ``flag`` for a lifecycle flag name, ``None`` for any other field."""
    if field in STATUS_FIELDS:
        return "assign"
    return "flag" if _flag_name(field) else None


def _uses(path: str, tree: ast.Module, index: PackageIndex | None = None) -> list[Use]:
    names = frozenset(_name(node) for node in ast.walk(tree) if isinstance(node, (ast.Name, ast.Attribute)))
    resolver = _Resolver(path, index or PackageIndex({path: tree}))
    uses: list[Use] = []
    for owner, function in functions(tree):
        scoped = resolver.scoped(owner, function)
        guards = _guards(resolver, owner, scoped)
        for node, scope in scoped:
            for hit in _status_uses(node):
                is_self = (
                    isinstance(hit.receiver, ast.Name) and hit.receiver.id in {"self", "cls"} and owner is not None
                )
                resolved = resolver.own(owner) if is_self else resolver.type_of(hit.receiver, owner, scope)
                arms = resolved.split("|") if resolved else [None]
                recomputed = hit.replaces and _recomputed(hit.value, function)
                guarded = None in guards or any(arm in guards for arm in arms)
                site = Site(
                    path,
                    getattr(node, "lineno", function.lineno),
                    f"{owner}.{function.name}" if owner else function.name,
                    _through(node) if hit.kind == "assign" else "",
                    "recompute" if recomputed and not guarded else "",
                )
                local = is_self and hit.kind == "assign"
                uses += [Use(hit.field, hit.kind, site, arm, names, local=local) for arm in arms]
        uses += _rebuilds(path, owner, function, resolver, scoped, names)
    return uses


def _guards(
    resolver: _Resolver, owner: str | None, scoped: list[tuple[ast.AST, dict[str, str | None]]]
) -> set[str | None]:
    """The types whose status a function compares or matches on; ``None`` stands for a receiver that does not resolve."""
    found: set[str | None] = set()
    for node, scope in scoped:
        sides = [node.left, *node.comparators] if isinstance(node, ast.Compare) else []
        sides += [node.subject] if isinstance(node, ast.Match) else []
        for side in sides:
            if isinstance(side, ast.Attribute) and side.attr in STATUS_FIELDS:
                resolved = resolver.type_of(side.value, owner, scope)
                found.update(resolved.split("|") if resolved else [None])
    return found


def _recomputed(value: ast.expr | None, function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when a stored value is computed (PIPE-GATES-R086.28): a call, or a local bound to a call in ``function``."""
    while isinstance(value, ast.Await):
        value = value.value
    if isinstance(value, ast.Call):
        return True
    if not isinstance(value, ast.Name):
        return False
    for node in ast.walk(function):
        bound = (
            node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        stored = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        while isinstance(stored, ast.Await):
            stored = stored.value
        if isinstance(stored, ast.Call) and any(isinstance(t, ast.Name) and t.id == value.id for t in bound):
            return True
    return False


def _rebuilds(
    path: str,
    owner: str | None,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    resolver: _Resolver,
    scoped: list[tuple[ast.AST, dict[str, str | None]]],
    names: frozenset[str],
) -> list[Use]:
    """A function that guards on a status and builds ``T(..., status=v)`` moves ``T`` by replacement.

    The guard is a comparison of the status of a ``T``; a comparison of another type's status, or
    of a receiver that does not resolve, is a mapping from something else to ``T``, and a status
    that is only read (passed on, printed) guards nothing.
    """
    read_types = {
        resolver.type_of(side.value, owner, scope)
        for node, scope in scoped
        if isinstance(node, ast.Compare)
        for side in (node.left, *node.comparators)
        if isinstance(side, ast.Attribute) and side.attr in STATUS_FIELDS
    }
    found: list[Use] = []
    for node, _ in scoped:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id[:1].isupper()):
            continue
        if node.func.id not in read_types:
            continue
        label = f"{owner}.{function.name}" if owner else function.name
        found += [
            Use(kw.arg, "assign", Site(path, node.lineno, label), node.func.id, names)
            for kw in node.keywords
            if kw.arg in STATUS_FIELDS
        ]
    return found


def _through(node: ast.AST) -> str:
    """The function an assignment stores the result of: ``x.status = transition(..)`` gives ``transition``."""
    value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) else None
    while isinstance(value, ast.Await):
        value = value.value
    return _name(value.func) if isinstance(value, ast.Call) else ""


#: A call that returns its first argument's elements (``sorted(xs)`` has the element type of ``xs``).
PASSTHROUGH = frozenset({"sorted", "list", "tuple", "set", "frozenset", "reversed"})
ELEMENT_GETTERS = frozenset({"get", "pop", "setdefault"})
COPIERS = frozenset({"model_copy", "copy", "deepcopy", "replace", "clone"})
#: ``asyncio.run(coro)`` and its kin return what the coroutine returns.
AWAITERS = frozenset({"run", "run_until_complete", "wait_for"})
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _display(node: ast.expr) -> bool:
    return isinstance(node, (ast.Tuple, ast.List, ast.Set))


class _Resolver:
    """Resolve the type of a receiver from annotations, constructors, copies and return types.

    A type is its bare class name. ``home`` records which module of the package index a
    name stands for in this run, so a field chain or a return type can cross files
    (PIPE-GATES-R086.21); two modules that define the same name in one function make that
    name ambiguous, and an ambiguous name resolves to nothing.
    """

    def __init__(self, path: str, index: PackageIndex) -> None:
        self.path, self.index = path, index
        self.home: dict[str, str] = {}

    def adopt(self, kind: str | None, context: str) -> str | None:
        """Canonical form of a type name read in module ``context``; a union is adopted arm by arm."""
        if not kind:
            return None
        if "|" in kind:
            arms = dict.fromkeys(arm for part in kind.split("|") if (arm := self.adopt(part, context)))
            return "|".join(arms) or None
        hit = self.index.resolve(context, kind)
        if hit is None or hit[1] not in hit[0].classes:
            return kind
        return hit[1] if self.home.setdefault(hit[1], hit[0].path) == hit[0].path else None

    def own(self, owner: str | None) -> str | None:
        """The class a method belongs to: it is this module's, whatever another module calls the same."""
        if owner:
            self.home[owner] = self.path
        return owner

    def _field_type(self, base: str | None, attribute: str) -> str | None:
        """The type of ``attribute`` on ``base``; on a union, the types the arms that have it give (PIPE-GATES-R086.23)."""
        found: dict[str, None] = {}
        for arm in (base or "").split("|"):
            info = self._class(arm)
            if info is not None and (kind := self.adopt(info.fields.get(attribute), info.module)):
                found.update(dict.fromkeys(kind.split("|")))
        return "|".join(found) or None

    def _class(self, kind: str | None) -> ClassInfo | None:
        if not kind or "|" in kind:
            return None
        module = self.home.get(kind)
        if module is None:
            hit = self.index.resolve(self.path, kind)
            module = hit[0].path if hit and hit[1] in hit[0].classes else None
        return self.index.modules[module].classes.get(kind) if module else None

    def scope(self, owner: str | None, function: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str | None]:
        """Local name -> type; ``name[]`` -> element type. A name bound to two types maps to ``None``."""
        scope: dict[str, str | None] = {}

        def bind(name: str, kind: str | None) -> None:
            scope[name] = kind if scope.get(name, kind) == kind else None

        for node in ast.walk(function):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                for arg in args:
                    bind(arg.arg, self.adopt(annotation_type(arg.annotation, owner), self.path))
                    bind(f"{arg.arg}[]", self.adopt(annotation_element(arg.annotation, owner), self.path))
        for node in sorted(
            (n for n in ast.walk(function) if hasattr(n, "lineno")),
            key=_position,
        ):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                kind = self.adopt(annotation_type(node.annotation, owner), self.path)
                bind(node.target.id, kind or (self.type_of(node.value, owner, scope) if node.value else None))
                element = self.adopt(annotation_element(node.annotation, owner), self.path)
                bind(
                    f"{node.target.id}[]",
                    element or (self._element_of(node.value, owner, scope) if node.value else None),
                )
            elif isinstance(node, ast.Assign):
                self._assign(node, owner, scope, bind)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                element = self._iterated(node.iter, owner, scope)
                direct = isinstance(node.target, ast.Name)
                for name in _bound_names(node.target):
                    # ``for x in records`` / ``records.values()`` binds x; ``for k, v in records.items()`` binds v.
                    bind(name, element if direct or name == _bound_names(node.target)[-1] else None)
            elif isinstance(node, ast.NamedExpr):
                bind(node.target.id, None)
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                for name in _bound_names(node.optional_vars):
                    bind(name, None)
        return scope

    def scoped(
        self, owner: str | None, function: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[tuple[ast.AST, dict[str, str | None]]]:
        """Every node of ``function`` with the scope that applies to it.

        A comprehension clause binds its variable inside that comprehension only, so two
        comprehensions that reuse a name for different types do not clash (PIPE-GATES-R086.20).
        """
        found: list[tuple[ast.AST, dict[str, str | None]]] = []
        stack: list[tuple[ast.AST, dict[str, str | None]]] = [(function, self.scope(owner, function))]
        while stack:
            node, view = stack.pop()
            found.append((node, view))
            if isinstance(node, COMPREHENSIONS):
                view = self._comprehension_view(node, owner, view)
            stack.extend((child, view) for child in reversed(list(ast.iter_child_nodes(node))))
        return found

    def _comprehension_view(
        self,
        node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
        owner: str | None,
        view: dict[str, str | None],
    ) -> dict[str, str | None]:
        inner = dict(view)
        for clause in node.generators:
            element = self._iterated(clause.iter, owner, inner)
            names = _bound_names(clause.target)
            for name in names:
                inner[name] = element if isinstance(clause.target, ast.Name) or name == names[-1] else None
                inner[f"{name}[]"] = None
        return inner

    def _assign(
        self, node: ast.Assign, owner: str | None, scope: dict[str, str | None], bind: Callable[..., None]
    ) -> None:
        kind = self.type_of(node.value, owner, scope)
        element = self._element_of(node.value, owner, scope)
        for target in node.targets:
            if isinstance(target, ast.Name):
                bind(target.id, kind)
                if element:
                    bind(f"{target.id}[]", element)
            elif isinstance(target, (ast.Tuple, ast.List)):
                items = self._unpacked(node.value, len(target.elts), owner, scope)
                for position, item in enumerate(target.elts):
                    if isinstance(item, ast.Name):
                        bind(item.id, items[position] if items else None)
                    else:
                        for name in _bound_names(item):
                            bind(name, None)

    def _unpacked(
        self, value: ast.expr, count: int, owner: str | None, scope: dict[str, str | None]
    ) -> tuple[str | None, ...]:
        """The element types of ``a, b = value``: a tuple display, or the callee's tuple return annotation (R086.22)."""
        while isinstance(value, ast.Await):
            value = value.value
        if (
            isinstance(value, ast.Tuple)
            and len(value.elts) == count
            and not any(isinstance(e, ast.Starred) for e in value.elts)
        ):
            return tuple(self.type_of(element, owner, scope) for element in value.elts)
        if isinstance(value, ast.Call):
            found = self._signature(value, owner, scope)
            if found is not None and len(found[0].items) == count:
                return tuple(self.adopt(kind, found[1]) for kind in found[0].items)
        return ()

    def _iterated(self, node: ast.expr, owner: str | None, scope: dict[str, str | None]) -> str | None:
        """The element type a ``for`` over ``node`` yields: a typed container, its ``values()`` or ``items()``."""
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"values", "items"}
        ):
            node = node.func.value
        return self._element_of(node, owner, scope)

    def _element_of(self, node: ast.expr | None, owner: str | None, scope: dict[str, str | None]) -> str | None:
        """The element type of a container expression: a typed name or field, a display, or a call that returns one."""
        if isinstance(node, ast.Await):
            return self._element_of(node.value, owner, scope)
        if isinstance(node, ast.Name):
            return scope.get(f"{node.id}[]")
        if isinstance(node, ast.Attribute):
            info = self._class(self.type_of(node.value, owner, scope))
            return self.adopt(info.elements.get(node.attr), info.module) if info else None
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return self._display_element(node, owner, scope)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            kind = self.type_of(node.elt, owner, self._comprehension_view(node, owner, scope))
            return kind if kind and "|" not in kind else None
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in PASSTHROUGH and node.args:
                return self._element_of(node.args[0], owner, scope)
            found = self._signature(node, owner, scope)
            return self.adopt(found[0].element, found[1]) if found else None
        return None

    def _display_element(
        self, node: ast.Tuple | ast.List | ast.Set, owner: str | None, scope: dict[str, str | None]
    ) -> str | None:
        """The one type every element of a display has (PIPE-GATES-R086.24); a mixed or unresolved display has none."""
        if not node.elts or any(isinstance(element, ast.Starred) for element in node.elts):
            return None
        kinds = {self.type_of(element, owner, scope) for element in node.elts}
        found = kinds.pop() if len(kinds) == 1 else None
        return found if found and "|" not in found else None

    def _signature(
        self, node: ast.Call, owner: str | None, scope: dict[str, str | None]
    ) -> tuple[Signature, str] | None:
        """The callee's signature and the module that defines it: a function, a method of a typed receiver, or ``mod.func``."""
        func = node.func
        if isinstance(func, ast.Name):
            hit = self.index.resolve(self.path, func.id)
            return (hit[0].functions[hit[1]], hit[0].path) if hit and hit[1] in hit[0].functions else None
        if not isinstance(func, ast.Attribute):
            return None
        info = self._class(self.type_of(func.value, owner, scope))
        if info is not None:
            return (info.methods[func.attr], info.module) if func.attr in info.methods else None
        if isinstance(func.value, ast.Name):
            module = self.index.module_named(self.path, func.value.id)
            if module is not None and func.attr in module.functions:
                return module.functions[func.attr], module.path
        return None

    def type_of(self, node: ast.expr | None, owner: str | None, scope: dict[str, str | None]) -> str | None:
        """The type ``node`` resolves to, or ``None``."""
        if isinstance(node, ast.Await):
            return self.type_of(node.value, owner, scope)
        if isinstance(node, ast.Name):
            return self.own(owner) if node.id in {"self", "cls"} and owner else scope.get(node.id)
        if isinstance(node, ast.Attribute):
            return self._field_type(self.type_of(node.value, owner, scope), node.attr)
        if isinstance(node, ast.Subscript):
            return self._element_of(node.value, owner, scope)
        if isinstance(node, ast.Call):
            return self._call_type(node, owner, scope)
        return None

    def _call_type(self, node: ast.Call, owner: str | None, scope: dict[str, str | None]) -> str | None:
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in COPIERS and node.args:
                return self.type_of(node.args[0], owner, scope)
            found = self._signature(node, owner, scope)
            if found is not None and found[0].returns:
                return self.adopt(found[0].returns, found[1])
            return self.adopt(func.id, self.path) if func.id[:1].isupper() else None
        if not isinstance(func, ast.Attribute):
            return None
        if (
            func.attr in AWAITERS
            and node.args
            and _name(func.value) == "asyncio"
            or func.attr == "run_until_complete"
            and node.args
        ):
            return self.type_of(node.args[0], owner, scope)
        if func.attr in COPIERS:
            return (
                self.type_of(node.args[0], owner, scope)
                if node.args and _name(func.value) in {"copy", "dataclasses"}
                else self.type_of(func.value, owner, scope)
            )
        if func.attr in ELEMENT_GETTERS:
            element = self._element_of(func.value, owner, scope)
            if element:
                return element
        found = self._signature(node, owner, scope)
        if found is not None and found[0].returns:
            return self.adopt(found[0].returns, found[1])
        if self.type_of(func.value, owner, scope):
            return None
        head = func.value
        if isinstance(head, ast.Name) and head.id[:1].isupper():
            return self.adopt(head.id, self.path)
        return (
            self.adopt(func.attr, self.path) if func.attr[:1].isupper() else None
        )  # ``module.Type(..)`` builds a ``Type``


def _position(node: ast.AST) -> tuple[int, int]:
    """Source position of a statement or expression."""
    return getattr(node, "lineno", 0), getattr(node, "col_offset", 0)


def _bound_names(target: ast.expr) -> list[str]:
    return [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]


def _status_uses(node: ast.AST) -> list[_Hit]:
    """Each status assignment, flag assignment or string compare at ``node``."""
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return [
            _Hit(t.attr, t.value, kind, node.value)
            for t in targets
            if isinstance(t, ast.Attribute) and (kind := _field_kind(t.attr))
        ]
    if isinstance(node, ast.Call):
        return _call_uses(node)
    if isinstance(node, ast.Compare):
        sides = [node.left, *node.comparators]
        if any(isinstance(s, ast.Constant) and isinstance(s.value, str) for s in sides):
            return [
                _Hit(s.attr, s.value, "compare")
                for s in sides
                if isinstance(s, ast.Attribute) and s.attr in STATUS_FIELDS
            ]
    return []


def _call_uses(node: ast.Call) -> list[_Hit]:
    """``setattr(x, 'status', v)``, ``replace(x, status=v)`` and ``x.model_copy(update={'status': v})``."""
    name = _name(node.func)
    receiver = node.args[0] if node.args else None
    if name in {"setattr", "__setattr__"} and len(node.args) >= 2 and _field_kind(_name(node.args[1])):
        field = _name(node.args[1])
        return [_Hit(field, receiver, _field_kind(field) or "", node.args[2] if len(node.args) > 2 else None)]
    if name == "replace":
        return [
            _Hit(kw.arg, receiver, kind, kw.value, True)
            for kw in node.keywords
            if kw.arg and (kind := _field_kind(kw.arg))
        ]
    if name == "model_copy" and isinstance(node.func, ast.Attribute):
        update = next((kw.value for kw in node.keywords if kw.arg == "update"), None)
        pairs = zip(update.keys, update.values, strict=False) if isinstance(update, ast.Dict) else []
        return [
            _Hit(_name(key), node.func.value, kind, value, True)
            for key, value in pairs
            if key is not None and (kind := _field_kind(_name(key)))
        ]
    return []
