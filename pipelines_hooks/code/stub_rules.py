"""AST stub detection and deferred-work comment markers, shared by no-stub and stubs.

A declared contract seam is the only accepted stub: ``[tool.pipelines_hooks.stubs]
declared_seams`` maps a file to the message constants its
``raise NotImplementedError(CONST)`` may use; each one is printed as NOT DONE.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Mapping
from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple

TODO_KEYWORDS = ("TODO", "FIXME", "WORK DEFERRED", "FUTURE WORK", "FUTURE ENHANCEMENT")
#: The word stub is ordinary prose ("stub it out"), so only the upper-case,
#: colon-terminated tag form counts.
STUB_TAG_RE = re.compile(r"\bSTUB\s*:")


def declared_seams(root: Path) -> Mapping[str, frozenset[str]]:
    raw = load_config(root).section("stubs").get("declared_seams", {})
    if not isinstance(raw, Mapping):
        raise ValueError("stubs.declared_seams must be a table")
    return {path: frozenset(string_tuple(values, f"stubs.declared_seams.{path}")) for path, values in raw.items()}


def is_not_implemented(node: ast.AST | None) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    return isinstance(target, ast.Name) and target.id == "NotImplementedError"


def seam_constant(node: ast.Raise) -> str | None:
    """``CONST`` of ``raise NotImplementedError(CONST)``, else ``None``."""
    exc = node.exc
    if isinstance(exc, ast.Call) and is_not_implemented(exc) and len(exc.args) == 1 and isinstance(exc.args[0], ast.Name):
        return exc.args[0].id
    return None


def is_stub_body(body: list[ast.stmt]) -> bool:
    """Only docstrings, ``...``, ``pass`` and ``raise NotImplementedError``."""
    for statement in body:
        constant = statement.value if isinstance(statement, ast.Expr) else None
        filler = isinstance(constant, ast.Constant) and (constant.value is Ellipsis or isinstance(constant.value, (str, bytes)))
        raises = isinstance(statement, ast.Raise) and is_not_implemented(statement.exc)
        if not (filler or raises or isinstance(statement, ast.Pass)):
            return False
    return True


def todo_comments(source: str) -> list[tuple[int, str]]:
    """``(line, keyword)`` for real ``#`` comment tokens only, never string text."""
    try:
        tokens = [t for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type == tokenize.COMMENT]
    except (tokenize.TokenError, SyntaxError):
        return []
    found = []
    for token in tokens:
        text = token.string[1:]
        found.extend((token.start[0], kw) for kw in TODO_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE))
        found.extend((token.start[0], "STUB") for _ in [0] if STUB_TAG_RE.search(text))
    return found


def is_abstract(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in function.decorator_list:
        name = decorator.attr if isinstance(decorator, ast.Attribute) else getattr(decorator, "id", "")
        if "abstract" in name:
            return True
    return False
