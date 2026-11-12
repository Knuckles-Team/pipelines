"""The Rust reader of the state-machine hooks: ``read_rust(path, source)``.

Built on a tree-sitter syntax tree. Every ``struct`` with a status field or a
lifecycle flag becomes one ``Machine``; ``enum`` items give the states. A
``self`` receiver resolves to the ``impl`` type; any other receiver counts
against each type of the file that declares the field, and ``loose_sites``
hands those to the hook for the rest of the crate. ``#[cfg(test)]`` modules,
``tests/`` and ``target/`` are skipped. A parse error cannot run (exit 2).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import PurePosixPath

import tree_sitter_rust
from tree_sitter import Language, Node, Parser, Tree

from pipelines_hooks.code.state_machine_model import (
    LIFECYCLE_TIMESTAMPS,
    STATUS_FIELDS,
    Edge,
    Machine,
    Site,
    Use,
    attach,
)
from pipelines_hooks.core.errors import CannotRun

TABLE_NAMES = frozenset({"LEGAL", "TRANSITIONS", "EDGES"})
FUNCTION_NAMES = frozenset({"transition", "apply", "step"})
STRING_TYPES = re.compile(r"^(&('\w+\s+)?str|String|str|[iu](8|16|32|64|128|size))$")
ENUM_SUFFIXES = ("Status", "State", "Phase", "Stage", "Lifecycle")
_OPTION = re.compile(r"^Option<(.*)>$")
_REFUSAL = re.compile(r"Result<.*,\s*(?:[\w:]+::)?(\w+Refused)\s*>")
_PARSER = Parser(Language(tree_sitter_rust.language()))


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", "replace") if node is not None and node.text is not None else ""


def _skipped(path: str) -> bool:
    return bool({"tests", "target"} & set(PurePosixPath(path).parts[:-1]))


#: ``#[cfg(..)] field,`` inside a struct pattern or definition (the grammar takes no attribute there).
_FIELD_ATTRIBUTE = re.compile(rb"#\[[^\]]*\](?=\s*(?:ref\s+|mut\s+)?\w+\s*[,}:])")
#: ``&_`` or ``&mut _`` as a fn-pointer parameter type (the grammar reads it as a pattern).
_REFERENCE_HOLE = re.compile(rb"(&\s*(?:mut\s+)?)_(?=\s*[,)>])")


def _normalise(data: bytes) -> bytes:
    """``data`` with field attributes blanked and ``&_`` named, byte for byte the same length."""
    blanked = _FIELD_ATTRIBUTE.sub(lambda m: re.sub(rb"[^\n]", b" ", m.group(0)), data)
    return _REFERENCE_HOLE.sub(rb"\1X", blanked)


def parse(path: str, data: bytes, *, strict: bool = True) -> Tree:
    """The syntax tree of ``data``; a parse error cannot run unless ``strict`` is off.

    With ``strict`` off the error-recovered tree is read as it is: the grammar
    lags the compiler (``_normalise`` covers the known gaps), and a
    file outside the change must not stop the census.

    ``Node.text`` reads the parsed buffer without owning it, so the caller holds
    ``data`` (and the tree) for as long as it reads nodes; a temporary buffer is
    freed under the nodes and a large file segfaults.
    """
    tree = _PARSER.parse(data)
    if tree.root_node.has_error:
        # Retry once with same-length rewrites of the constructs the grammar lacks.
        # Offsets, and so line numbers, are unchanged; a file that still fails is not read.
        data = _normalise(data)
        tree = _PARSER.parse(data)
    if strict and tree.root_node.has_error:
        raise CannotRun(f"{path}: Rust source does not parse")
    return tree


def _items(node: Node) -> Iterator[Node]:
    """Every item below ``node`` except the bodies of ``#[cfg(test)]`` modules."""
    cfg_test = False
    for child in node.named_children:
        if child.type == "attribute_item":
            cfg_test = cfg_test or "cfg(test)" in _text(child).replace(" ", "")
            continue
        if child.type == "mod_item" and cfg_test:
            cfg_test = False
            continue
        cfg_test = False
        yield child
        body = child.child_by_field_name("body")
        if child.type in {"mod_item", "impl_item"} and body is not None:
            yield from _items(body)


def read_rust(path: str, source: str, *, strict: bool = True) -> list[Machine]:
    """One ``Machine`` per struct with a status field or lifecycle flag."""
    if _skipped(path):
        return []
    data = source.encode("utf-8")
    tree = parse(path, data, strict=strict)
    items = list(_items(tree.root_node))
    enums = {
        _text(i.child_by_field_name("name")): tuple(
            _text(v.child_by_field_name("name"))
            for v in i.named_children[-1].named_children
            if v.type == "enum_variant"
        )
        for i in items
        if i.type == "enum_item"
    }
    consts = {
        _text(i.child_by_field_name("name")): i.child_by_field_name("value")
        for i in items
        if i.type in {"const_item", "static_item"}
    }
    function = _transition(items)
    machines = [m for i in items if i.type == "struct_item" for m in [_machine(path, i, enums, consts, function)] if m]
    for use in _uses(path, items, frozenset(re.findall(r"\w+", source))):
        for machine in machines:
            if use.field == machine.status_field and use.receiver in {None, machine.type_name}:
                attach(machine, use)
    return machines


def loose_sites(path: str, source: str, *, strict: bool = True) -> list[Use]:
    """The uses whose receiver is not ``self``: the hook matches them crate-wide."""
    if _skipped(path):
        return []
    data = source.encode("utf-8")
    tree = parse(path, data, strict=strict)
    items = list(_items(tree.root_node))
    return [use for use in _uses(path, items, frozenset(re.findall(r"\w+", source))) if use.receiver is None]


def _kind(type_text: str, enums: dict[str, tuple[str, ...]]) -> tuple[str, str, bool]:
    """``(type, kind, nullable)`` of a field type."""
    match = _OPTION.match(type_text)
    inner = match.group(1).strip() if match else type_text
    name = inner.split("::")[-1]
    if STRING_TYPES.match(inner):
        return inner, "string", bool(match)
    return name, ("enum" if name in enums or name.endswith(ENUM_SUFFIXES) else ""), bool(match)


def _machine(
    path: str,
    item: Node,
    enums: dict[str, tuple[str, ...]],
    consts: dict[str, Node | None],
    function: dict[str, tuple[str, str]],
) -> Machine | None:
    body = item.child_by_field_name("body")
    fields = [
        (_text(f.child_by_field_name("name")), _text(f.child_by_field_name("type")))
        for f in (body.named_children if body is not None else [])
        if f.type == "field_declaration"
    ]
    flags = tuple(
        name
        for name, type_text in fields
        if name.startswith("is_")
        or name.endswith("_requested")
        or name == "terminal"
        or (name in LIFECYCLE_TIMESTAMPS and _kind(type_text, enums)[2])
    )
    status = next(((n, t) for n, t in fields if n in STATUS_FIELDS), None)
    if status is None and not flags:
        return None
    name = _text(item.child_by_field_name("name"))
    machine = Machine("rust", path, item.start_point.row + 1, name, flags=flags)
    if status is not None:
        machine.status_field = status[0]
        machine.status_type, machine.status_kind, _ = _kind(status[1], enums)
        _declare(machine, consts, function.get(name), enums)
    return machine


def _declare(
    machine: Machine,
    consts: dict[str, Node | None],
    function: tuple[str, str] | None,
    enums: dict[str, tuple[str, ...]],
) -> None:
    table = next((n for n in ("TRANSITIONS", "LEGAL", "EDGES") if n in consts), None)
    if table is not None:
        machine.table, machine.edges = table, _edges(consts[table])
    if function is not None:
        machine.function, machine.refusal = function
    initial = consts.get("INITIAL")
    machine.initial = _token(initial) if initial is not None else None
    terminal = consts.get("TERMINALS", consts.get("TERMINAL"))
    machine.terminals = tuple(_token(n) for n in _elements(terminal)) if terminal is not None else ()
    machine.states = enums.get(machine.status_type or "", ())


def _elements(node: Node | None) -> list[Node]:
    while node is not None and node.type == "reference_expression":
        node = node.child_by_field_name("value")
    if node is None:
        return []
    return list(node.named_children) if node.type in {"array_expression", "tuple_expression"} else [node]


def _token(node: Node) -> str:
    """``State::Done`` -> ``Done``; ``"start"`` -> ``start``."""
    if node.type == "string_literal":
        return _text(node)[1:-1]
    return _text(node).split("::")[-1]


def _edges(value: Node | None) -> tuple[Edge, ...]:
    edges: list[Edge] = []
    for element in _elements(value):
        parts = [_token(p) for p in element.named_children] if element.type == "tuple_expression" else []
        if len(parts) == 3:
            edges.append((parts[0], parts[1], parts[2]))
        elif len(parts) == 2:
            edges.append((parts[0], parts[1], parts[1]))
    return tuple(edges)


def _transition(items: list[Node]) -> dict[str, tuple[str, str]]:
    """impl type -> (``Type.fn``, refusal) for ``transition``/``apply``/``step`` returning ``Result<_, *Refused>``."""
    found: dict[str, tuple[str, str]] = {}
    for item in (i for i in items if i.type == "function_item" and i.parent is not None):
        owner = _impl_type(item)
        name = _text(item.child_by_field_name("name"))
        match = _REFUSAL.search(_text(item.child_by_field_name("return_type")))
        if owner and name in FUNCTION_NAMES and match:
            found.setdefault(owner, (f"{owner}.{name}", match.group(1)))
    return found


def _impl_type(node: Node) -> str:
    parent = node.parent
    while parent is not None and parent.type != "impl_item":
        parent = parent.parent
    return _text(parent.child_by_field_name("type")).split("<")[0] if parent is not None else ""


def _uses(path: str, items: list[Node], names: frozenset[str]) -> list[Use]:
    uses: list[Use] = []
    for item in (i for i in items if i.type == "function_item"):
        owner = _impl_type(item)
        name = _text(item.child_by_field_name("name"))
        label = f"{owner}.{name}" if owner else name
        for node, field, receiver, kind in _walk_uses(item):
            cls = owner if receiver == "self" else (receiver if receiver[:1].isupper() else None)
            uses.append(Use(field, kind, Site(path, node.start_point.row + 1, label), cls, names))
    return uses


def _field_of(node: Node | None) -> tuple[str, str] | None:
    """``(field, receiver)`` of ``x.status`` (or ``&mut x.status``)."""
    while node is not None and node.type in {"reference_expression", "mutable_specifier"}:
        node = node.child_by_field_name("value")
    if node is None or node.type != "field_expression":
        return None
    field = _text(node.child_by_field_name("field"))
    return (field, _text(node.child_by_field_name("value"))) if field in STATUS_FIELDS else None


def _walk_uses(root: Node) -> Iterator[tuple[Node, str, str, str]]:
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(reversed(node.named_children))
        yield from _node_uses(node)


def _node_uses(node: Node) -> list[tuple[Node, str, str, str]]:
    if node.type in {"assignment_expression", "compound_assignment_expr"}:
        hit = _field_of(node.child_by_field_name("left"))
        return [(node, hit[0], hit[1], "assign")] if hit else []
    if node.type == "binary_expression" and _text(node.child_by_field_name("operator")) in {"==", "!="}:
        sides = [node.child_by_field_name("left"), node.child_by_field_name("right")]
        if any(s is not None and s.type == "string_literal" for s in sides):
            return [(node, h[0], h[1], "compare") for h in map(_field_of, sides) if h]
    if node.type == "call_expression" and _text(node.child_by_field_name("function")).endswith("replace"):
        args = node.child_by_field_name("arguments")
        hit = _field_of(args.named_children[0]) if args is not None and args.named_children else None
        return [(node, hit[0], hit[1], "assign")] if hit else []
    if node.type == "struct_expression":
        return _struct_update(node)
    return []


def _struct_update(node: Node) -> list[tuple[Node, str, str, str]]:
    """``Type { status: v, ..base }`` sets the field on ``Type``."""
    body = node.child_by_field_name("body")
    children = body.named_children if body is not None else []
    if not any(c.type == "base_field_initializer" for c in children):
        return []
    owner = _text(node.child_by_field_name("name")).split("::")[-1]
    owner = "self" if owner == "Self" else owner
    return [
        (node, _text(c.child_by_field_name("field")), owner, "assign")
        for c in children
        if c.type == "field_initializer" and _text(c.child_by_field_name("field")) in STATUS_FIELDS
    ]
