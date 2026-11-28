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
from pathlib import PurePosixPath

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


def read_python(path: str, tree: ast.Module) -> list[Machine]:
    """One ``Machine`` per class with a status field or lifecycle flag."""
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
    for use in _uses(path, tree):
        for machine in machines:
            if use.field == machine.status_field and use.receiver == machine.type_name:
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


def loose_sites(path: str, tree: ast.Module) -> list[Use]:
    """The uses whose receiver is not ``self``: the hook matches them by resolved type, package-wide."""
    return [] if is_test_file(path) else [use for use in _uses(path, tree) if not use.local]


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


def _name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _name(node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.unparse(node) if node is not None else ""


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


def _uses(path: str, tree: ast.Module) -> list[Use]:
    names = frozenset(_name(node) for node in ast.walk(tree) if isinstance(node, (ast.Name, ast.Attribute)))
    resolver = _Resolver(tree)
    uses: list[Use] = []
    for owner, function in _functions(tree):
        scope = resolver.scope(owner, function)
        for node in ast.walk(function):
            for field, receiver, kind in _status_uses(node):
                is_self = isinstance(receiver, ast.Name) and receiver.id in {"self", "cls"} and owner is not None
                resolved = owner if is_self else resolver.type_of(receiver, owner, scope)
                site = Site(
                    path,
                    getattr(node, "lineno", function.lineno),
                    f"{owner}.{function.name}" if owner else function.name,
                )
                uses.append(Use(field, kind, site, resolved, names, local=is_self))
        uses += _rebuilds(path, owner, function, resolver, scope, names)
    return uses


def _rebuilds(
    path: str,
    owner: str | None,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    resolver: _Resolver,
    scope: dict[str, str | None],
    names: frozenset[str],
) -> list[Use]:
    """A function that guards on a status and builds ``T(..., status=v)`` moves ``T`` by replacement.

    The guard is a comparison of the status of a ``T``; a comparison of another type's status, or
    of a receiver that does not resolve, is a mapping from something else to ``T``, and a status
    that is only read (passed on, printed) guards nothing.
    """
    read_types = {
        resolver.type_of(side.value, owner, scope)
        for node in ast.walk(function)
        if isinstance(node, ast.Compare)
        for side in (node.left, *node.comparators)
        if isinstance(side, ast.Attribute) and side.attr in STATUS_FIELDS
    }
    found: list[Use] = []
    for node in ast.walk(function):
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


def _functions(tree: ast.Module) -> list[tuple[str | None, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found: list[tuple[str | None, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((None, node))
        elif isinstance(node, ast.ClassDef):
            found += [(node.name, s) for s in node.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return found


MAPPINGS = frozenset({"dict", "Dict", "Mapping", "MutableMapping", "defaultdict", "OrderedDict"})
CONTAINERS = MAPPINGS | frozenset({"list", "List", "Sequence", "set", "Set", "frozenset", "tuple", "Tuple"})
ELEMENT_GETTERS = frozenset({"get", "pop", "setdefault"})
OPAQUE_TYPES = frozenset({"Any", "object", ""})
COPIERS = frozenset({"model_copy", "copy", "deepcopy", "replace", "clone"})


def _annotation_type(annotation: ast.expr | None, owner: str | None) -> str | None:
    """The single type an annotation names, or ``None`` for a union, container or ``Any``."""
    if annotation is None:
        return None
    inner, _ = _strip_optional(annotation)
    if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
        try:
            return _annotation_type(ast.parse(inner.value, mode="eval").body, owner)
        except SyntaxError:
            return None
    if isinstance(inner, ast.Subscript) and _name(inner.value) == "Annotated":
        first = inner.slice.elts[0] if isinstance(inner.slice, ast.Tuple) and inner.slice.elts else inner.slice
        return _annotation_type(first, owner)
    if not isinstance(inner, (ast.Name, ast.Attribute)):
        return None
    name = _name(inner)
    if name == "Self":
        return owner
    return None if name in OPAQUE_TYPES else name


class _Resolver:
    """Resolve the type of a receiver from annotations, constructors, copies and return types."""

    def __init__(self, tree: ast.Module) -> None:
        self.returns: dict[str, str] = {}
        self.fields: dict[str, dict[str, str]] = {}
        #: Class -> field -> the element type of a ``dict[K, V]`` or ``list[V]`` field.
        self.elements: dict[str, dict[str, str]] = {}
        for owner, function in _functions(tree):
            found = _annotation_type(function.returns, owner)
            if found:
                self.returns[f"{owner}.{function.name}" if owner else function.name] = found
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                self.fields[node.name] = self._class_fields(node)
                self.elements[node.name] = self._class_elements(node)

    @staticmethod
    def _class_elements(node: ast.ClassDef) -> dict[str, str]:
        """Field name -> element type for ``x: dict[K, V]`` / ``x: list[V]`` (class level or ``self.x: ...``)."""
        found: dict[str, str] = {}
        for stmt in ast.walk(node):
            if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.annotation, ast.Subscript)):
                continue
            target = stmt.target
            key = target.id if isinstance(target, ast.Name) and stmt in node.body else None
            if isinstance(target, ast.Attribute) and _name(target.value) == "self":
                key = target.attr
            container = _name(stmt.annotation.value)
            items = (
                stmt.annotation.slice.elts if isinstance(stmt.annotation.slice, ast.Tuple) else [stmt.annotation.slice]
            )
            if key and container in CONTAINERS and items:
                kind = _annotation_type(items[-1] if container in MAPPINGS else items[0], node.name)
                if kind:
                    found.setdefault(key, kind)
        return found

    def _element_of(self, node: ast.expr, owner: str | None, scope: dict[str, str | None]) -> str | None:
        """The element type of ``self.records`` when it is a typed container field."""
        if isinstance(node, ast.Attribute):
            base = self.type_of(node.value, owner, scope)
            return self.elements.get(base or "", {}).get(node.attr)
        return None

    @staticmethod
    def _class_fields(node: ast.ClassDef) -> dict[str, str]:
        """Field name -> type from class-level and ``self.x: T`` annotations."""
        found: dict[str, str] = {}
        for stmt in ast.walk(node):
            if not isinstance(stmt, ast.AnnAssign):
                continue
            target = stmt.target
            if isinstance(target, ast.Name) and stmt in node.body:
                key = target.id
            elif isinstance(target, ast.Attribute) and _name(target.value) == "self":
                key = target.attr
            else:
                continue
            kind = _annotation_type(stmt.annotation, node.name)
            if kind:
                found.setdefault(key, kind)
        return found

    def scope(self, owner: str | None, function: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str | None]:
        """Local name -> type; a name bound to two types, or by a loop or ``with``, maps to ``None``."""
        scope: dict[str, str | None] = {}

        def bind(name: str, kind: str | None) -> None:
            scope[name] = kind if scope.get(name, kind) == kind else None

        for node in ast.walk(function):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                for arg in args:
                    bind(arg.arg, _annotation_type(arg.annotation, owner))
        for node in sorted(
            (n for n in ast.walk(function) if hasattr(n, "lineno")),
            key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)),
        ):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                kind = _annotation_type(node.annotation, owner)
                bind(node.target.id, kind or (self.type_of(node.value, owner, scope) if node.value else None))
            elif isinstance(node, ast.Assign):
                kind = self.type_of(node.value, owner, scope)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bind(target.id, kind)
                    elif isinstance(target, (ast.Tuple, ast.List)):
                        for name in _bound_names(target):
                            bind(name, None)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                for name in _bound_names(node.target):
                    bind(name, None)
            elif isinstance(node, ast.NamedExpr):
                bind(node.target.id, None)
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                for name in _bound_names(node.optional_vars):
                    bind(name, None)
        return scope

    def type_of(self, node: ast.expr | None, owner: str | None, scope: dict[str, str | None]) -> str | None:
        """The type ``node`` resolves to, or ``None``."""
        if isinstance(node, ast.Await):
            return self.type_of(node.value, owner, scope)
        if isinstance(node, ast.Name):
            return owner if node.id in {"self", "cls"} and owner else scope.get(node.id)
        if isinstance(node, ast.Attribute):
            base = self.type_of(node.value, owner, scope)
            return self.fields.get(base or "", {}).get(node.attr)
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
            return self.returns.get(func.id) or (func.id if func.id[:1].isupper() else None)
        if not isinstance(func, ast.Attribute):
            return None
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
        base = self.type_of(func.value, owner, scope)
        if base:
            return self.returns.get(f"{base}.{func.attr}")
        head = func.value
        return head.id if isinstance(head, ast.Name) and head.id[:1].isupper() else None


def _bound_names(target: ast.expr) -> list[str]:
    return [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]


def _status_uses(node: ast.AST) -> list[tuple[str, ast.expr | None, str]]:
    """``(field, receiver expression, kind)`` for each status assignment or string compare at ``node``."""
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return [
            (t.attr, t.value, "assign") for t in targets if isinstance(t, ast.Attribute) and t.attr in STATUS_FIELDS
        ]
    if isinstance(node, ast.Call):
        return _call_uses(node)
    if isinstance(node, ast.Compare):
        sides = [node.left, *node.comparators]
        if any(isinstance(s, ast.Constant) and isinstance(s.value, str) for s in sides):
            return [
                (s.attr, s.value, "compare") for s in sides if isinstance(s, ast.Attribute) and s.attr in STATUS_FIELDS
            ]
    return []


def _call_uses(node: ast.Call) -> list[tuple[str, ast.expr | None, str]]:
    """``setattr(x, 'status', v)``, ``replace(x, status=v)`` and ``x.model_copy(update={'status': v})``."""
    name = _name(node.func)
    receiver = node.args[0] if node.args else None
    if name in {"setattr", "__setattr__"} and len(node.args) >= 2 and _name(node.args[1]) in STATUS_FIELDS:
        return [(_name(node.args[1]), receiver, "assign")]
    if name == "replace":
        return [(kw.arg, receiver, "assign") for kw in node.keywords if kw.arg in STATUS_FIELDS]
    if name == "model_copy" and isinstance(node.func, ast.Attribute):
        update = next((kw.value for kw in node.keywords if kw.arg == "update"), None)
        keys = update.keys if isinstance(update, ast.Dict) else []
        return [(_name(key), node.func.value, "assign") for key in keys if _name(key) in STATUS_FIELDS]
    return []
