"""event-loop-blocking: no blocking call ADDED directly inside an ``async def``.

A static heuristic: a known blocking call (engine/KG read or write, blocking
file I/O, ``subprocess``, synchronous HTTP, ``time.sleep``) written as a
literal call inside an ``async def`` body with no thread hop. A nested function
passed by bare reference to a hop call (``asyncio.to_thread``,
``run_in_executor``, ...) is exempt because it runs off-loop; an un-hopped
nested closure runs on the loop and is scanned. ``time.sleep`` in an
``async def`` is enforced at an absolute zero. Test paths are not scanned.
Plain-``def`` handlers and calls hidden behind helpers are out of scope.
"""

from __future__ import annotations

import ast

from pipelines_hooks.code import sitegate
from pipelines_hooks.code.event_loop_calls import call_label, hopped_names, label_shape

_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _walk(node: ast.AST, *, protected: set[str], found: list[tuple[int, str]]) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _NESTED) and getattr(child, "name", "<lambda>") in protected:
            continue
        label = call_label(child) if isinstance(child, ast.Call) else None
        if label:
            found.append((child.lineno, label))
        _walk(child, protected=protected, found=found)


def scan_source(rel: str, source: str) -> list[sitegate.Site]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            _walk(node, protected=hopped_names(node), found=found)
    return [sitegate.Site(rel, line, label_shape(label), label) for line, label in sorted(set(found))]


def _not_test(rel: str) -> bool:
    return "/tests/" not in f"/{rel}" and not rel.rsplit("/", 1)[-1].startswith("test_")


GATE = sitegate.SiteGate(
    name="event-loop-blocking",
    scan_source=scan_source,
    hard_zero=frozenset({"time_sleep"}),
    include=_not_test,
    remedy=(
        "Hop the blocking call off the event loop (asyncio.to_thread, loop.run_in_executor, "
        "run_blocking_ordered) or use the async API; await asyncio.sleep instead of time.sleep."
    ),
)


def main(argv: list[str]) -> int:
    return sitegate.run(GATE, argv)
