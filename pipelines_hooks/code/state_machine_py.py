"""The Python reader of the state-machine hooks: ``read_python(path, tree)``.

Built on the ``ast`` module. Every class with a status field or a lifecycle
flag becomes one ``Machine``. ``self`` assignments resolve to the enclosing
class; any other receiver counts against each type of the file that declares
the field, and ``loose_sites`` hands those to the hook for the rest of the
package. Test files are skipped.
"""

from __future__ import annotations

import ast
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
    module_tables = _tables(tree.body)
    module_function = _transition(tree.body, None)
    machines = [
        machine
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name not in enums
        for machine in [_machine(path, node, enums, module_tables, module_function, _constants(tree.body))]
        if machine is not None
    ]
    for use in _uses(path, tree):
        for machine in machines:
            if use.field != machine.status_field:
                continue
            if use.receiver is not None and use.receiver != machine.type_name:
                continue
            attach(machine, use)
    return machines


def loose_sites(path: str, tree: ast.Module) -> list[Use]:
    """The uses whose receiver is not ``self``: the hook matches them package-wide."""
    return [] if is_test_file(path) else [use for use in _uses(path, tree) if use.receiver is None]


def _enum_members(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(_name(base) in ENUM_BASES for base in node.bases):
            found[node.name] = tuple(
                target.id
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                for target in stmt.targets
                if isinstance(target, ast.Name)
            )
    return found


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
    enums: dict[str, tuple[str, ...]],
    module_tables: list[tuple[str, tuple[Edge, ...]]],
    module_function: tuple[str, str] | None,
    module_constants: tuple[str | None, tuple[str, ...]],
) -> Machine | None:
    fields = _fields(node)
    status = next((stmt for stmt in fields if _name(stmt.target) in STATUS_FIELDS), None)
    flags = tuple(_name(stmt.target) for stmt in fields if _flag(stmt))
    if status is None and not flags:
        return None
    machine = Machine("python", path, node.lineno, node.name, flags=flags)
    if status is not None:
        machine.status_field = _name(status.target)
        machine.status_type, machine.status_kind = _kind(status.annotation, enums)
        tables = _tables(node.body) or module_tables
        if tables:
            machine.table, machine.edges = tables[0]
        function = _transition(node.body, node.name) or module_function
        own = _constants(node.body)
        constants = (own[0] or module_constants[0], own[1] or module_constants[1])
        if function is not None:
            machine.function, machine.refusal = function
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


def _tables(body: list[ast.stmt]) -> list[tuple[str, tuple[Edge, ...]]]:
    found = []
    for stmt in body:
        target = stmt.targets[0] if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 else None
        target = stmt.target if isinstance(stmt, ast.AnnAssign) else target
        value = stmt.value if isinstance(stmt, (ast.Assign, ast.AnnAssign)) else None
        if isinstance(target, ast.Name) and target.id in TABLE_NAMES and value is not None:
            found.append((target.id, _edges(value)))
    return found


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


def _transition(body: list[ast.stmt], owner: str | None) -> tuple[str, str] | None:
    """The transition function and the ``*Refused`` class it raises."""
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name in FUNCTION_NAMES:
            for raise_node in (n for n in ast.walk(stmt) if isinstance(n, ast.Raise)):
                refusal = _name(raise_node.exc.func if isinstance(raise_node.exc, ast.Call) else raise_node.exc)
                if refusal.endswith("Refused"):
                    return (f"{owner}.{stmt.name}" if owner else stmt.name), refusal
    return None


def _uses(path: str, tree: ast.Module) -> list[Use]:
    names = frozenset(_name(node) for node in ast.walk(tree) if isinstance(node, (ast.Name, ast.Attribute)))
    uses: list[Use] = []
    for owner, function in _functions(tree):
        for node in ast.walk(function):
            for field, receiver, kind in _status_uses(node):
                cls = owner if receiver == "self" else None
                site = Site(
                    path,
                    getattr(node, "lineno", function.lineno),
                    f"{owner}.{function.name}" if owner else function.name,
                )
                uses.append(Use(field, kind, site, cls, names))
    return uses


def _functions(tree: ast.Module) -> list[tuple[str | None, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found: list[tuple[str | None, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((None, node))
        elif isinstance(node, ast.ClassDef):
            found += [(node.name, s) for s in node.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return found


def _receiver(node: ast.expr) -> str:
    return node.id if isinstance(node, ast.Name) else ""


def _status_uses(node: ast.AST) -> list[tuple[str, str, str]]:
    """``(field, receiver, kind)`` for each status assignment or string compare at ``node``."""
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return [
            (t.attr, _receiver(t.value), "assign")
            for t in targets
            if isinstance(t, ast.Attribute) and t.attr in STATUS_FIELDS
        ]
    if isinstance(node, ast.Call):
        return _call_uses(node)
    if isinstance(node, ast.Compare):
        sides = [node.left, *node.comparators]
        if any(isinstance(s, ast.Constant) and isinstance(s.value, str) for s in sides):
            return [
                (s.attr, _receiver(s.value), "compare")
                for s in sides
                if isinstance(s, ast.Attribute) and s.attr in STATUS_FIELDS
            ]
    return []


def _call_uses(node: ast.Call) -> list[tuple[str, str, str]]:
    """``setattr(x, 'status', v)``, ``replace(x, status=v)`` and ``x.model_copy(update={'status': v})``."""
    name = _name(node.func)
    receiver = _receiver(node.args[0]) if node.args else ""
    if name == "setattr" and len(node.args) >= 2 and _name(node.args[1]) in STATUS_FIELDS:
        return [(_name(node.args[1]), receiver, "assign")]
    if name == "replace":
        return [(kw.arg, receiver, "assign") for kw in node.keywords if kw.arg in STATUS_FIELDS]
    if name == "model_copy" and isinstance(node.func, ast.Attribute):
        update = next((kw.value for kw in node.keywords if kw.arg == "update"), None)
        keys = update.keys if isinstance(update, ast.Dict) else []
        owner = _receiver(node.func.value)
        return [(_name(key), owner, "assign") for key in keys if _name(key) in STATUS_FIELDS]
    return []
