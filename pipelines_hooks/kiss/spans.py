"""Locate a named function's exact source span, for Python and Rust.

Returned spans are ``(start_line, end_line, text)`` in file order; a
same-named function found N times is matched to the N-th in the other tree by
ordinal. Unparseable or unlexable source yields no spans, which makes every
finding in it attributable (fail closed).
"""

from __future__ import annotations

import ast
import re

from pipelines_hooks.rust.balance import balanced_span_from
from pipelines_hooks.rust.mask import RustLexError, code_mask


def python_spans(source: str, name: str) -> list[tuple[int, int, str]]:
    """Every ``def``/``async def`` named ``name``, decorators included."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    lines = source.splitlines(keepends=True)
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            end = node.end_lineno or node.lineno
            spans.append((start, end, "".join(lines[start - 1 : end])))
    return sorted(spans)


def _body_open(masked: str, start: int) -> int | None:
    """First top-level ``{`` after a ``fn name`` match; ``None`` for a declaration."""
    depth = 0
    for index in range(start, len(masked)):
        char = masked[index]
        if char in "{;" and depth <= 0:
            return index if char == "{" else None
        depth += (char == "(") - (char == ")")
    return None


def _rust_spans(source: str, name: str) -> list[tuple[int, int, str]]:
    masked = code_mask(source)
    spans = []
    for match in re.finditer(r"\bfn\s+" + re.escape(name) + r"\s*[(<]", masked):
        body = _body_open(masked, match.end())
        if body is None:
            terminator = masked.find(";", match.end())
            end = terminator if terminator != -1 else len(source) - 1
        else:
            end = balanced_span_from(masked, body, opener="{", closer="}")
        start = source.rfind("\n", 0, match.start()) + 1
        spans.append((source.count("\n", 0, match.start()) + 1, source.count("\n", 0, end) + 1, source[start : end + 1]))
    return spans


def rust_spans(source: str, name: str) -> list[tuple[int, int, str]]:
    """Every ``fn name`` in comment- and literal-masked Rust source."""
    try:
        return _rust_spans(source, name)
    except RustLexError:
        return []


def spans_for(path: str):
    """The span finder for a KISS-scanned path."""
    return rust_spans if path.endswith(".rs") else python_spans
