"""The test-binding rule of the state-machine hooks: ``bind_tests(machine, test_files)``.

Each edge ``(from, event, to)`` of a declared table needs a test whose
snake-case name, or one of whose ``parametrize`` ids, holds the from-state and
the event. A refusal test has ``refus`` or ``illegal`` in its name and names the
refusal type in its body. Python tests are read with ``ast``; Rust ``#[test]``
functions are read from their source text.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pipelines_hooks.code.state_machine_model import Machine

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_RUST_TEST = re.compile(r"#\[(?:tokio::)?test[^\]]*\]\s*(?:async\s+)?fn\s+(\w+)")


@dataclass(frozen=True)
class Case:
    """One test function: its name, its parametrize ids, and the names its body uses."""

    name: str
    ids: tuple[str, ...]
    body: str


def snake(token: str) -> str:
    """``InProgress`` -> ``in_progress``; ``RUNNING`` -> ``running``."""
    return _CAMEL.sub("_", token).replace("-", "_").lower()


def read_cases(path: str, source: str) -> list[Case]:
    """The test functions of one Python or Rust test file."""
    if path.endswith(".rs"):
        return _rust_cases(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [
        Case(node.name, _ids(node), ast.unparse(node))
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")
    ]


def _ids(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    """String ids of ``parametrize`` (``ids=[...]`` and ``pytest.param(..., id=...)``)."""
    found: list[str] = []
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call) and ast.unparse(decorator.func).endswith("parametrize"):
            for sub in ast.walk(decorator):
                if isinstance(sub, ast.keyword) and sub.arg in {"ids", "id"}:
                    found += [
                        c.value for c in ast.walk(sub.value) if isinstance(c, ast.Constant) and isinstance(c.value, str)
                    ]
    return tuple(found)


def _rust_cases(source: str) -> list[Case]:
    matches = list(_RUST_TEST.finditer(source))
    ends = [m.start() for m in matches[1:]] + [len(source)]
    return [Case(m.group(1), (), source[m.start() : end]) for m, end in zip(matches, ends, strict=True)]


def names_edge(case: Case, source: str, event: str) -> bool:
    """Whether the test name or one parametrize id holds both tokens."""
    wanted = (snake(source), snake(event))
    return any(all(token in snake(label) for token in wanted) for label in (case.name, *case.ids))


def is_refusal_test(case: Case, refusal: str | None) -> bool:
    name = case.name.lower()
    return ("refus" in name or "illegal" in name) and refusal is not None and refusal in case.body


def bind_tests(machine: Machine, test_files: Sequence[tuple[str, str]]) -> None:
    """Fill ``untested_edges`` and ``refusal_tested`` of a declared machine."""
    if not machine.declared:
        return
    cases = [case for path, source in test_files for case in read_cases(path, source)]
    machine.untested_edges = [
        (source, event)
        for source, event, _ in machine.edges
        if not any(names_edge(case, source, event) for case in cases)
    ]
    refusals = [case for case in cases if is_refusal_test(case, machine.refusal)]
    machine.refusal_tested = bool(refusals)
    machine.refused_cells = {
        (state, event)
        for case in refusals
        for state in machine.all_states()
        for event in {event for _, event, _ in machine.edges}
        if names_edge(case, state, event)
    }
    machine.product_refusal_test = any(iterates_product(case, machine.table) for case in refusals)
    machine.bound = True


def iterates_product(case: Case, table: str | None) -> bool:
    """A refusal test whose body loops over the table constant's state-by-event product."""
    body = case.body
    return table is not None and table in body and ("product(" in body or body.count("for ") >= 2)
