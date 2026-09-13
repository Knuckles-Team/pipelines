"""Locate a function's normalized text for the reviewed-distinct register.

Works for Rust (``fn NAME``, brace-balanced body) and Python (``def NAME``,
indentation-delimited body). Whitespace runs collapse, so reformatting a
signature does not force a re-review while any token change does.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def _declaration(path: Path, name: str) -> re.Pattern[str]:
    if path.suffix in {".py", ".pyi"}:
        return re.compile(rf"^\s*(?:async\s+)?def\s+{re.escape(name)}\b")
    return re.compile(rf"\bfn\s+{re.escape(name)}\b")


def _declaration_start(lines: list[str], line: int, declaration: re.Pattern[str]) -> int | None:
    """Prefer a hit near the (HEAD-relative) hint, then anywhere in the file."""
    near = range(max(0, line - 3), min(len(lines), line + 3))
    for candidate in [*near, *range(len(lines))]:
        if declaration.search(lines[candidate]):
            return candidate
    return None


def _brace_block(lines: list[str], start: int) -> list[str]:
    depth, seen, collected = 0, False, []
    for text in lines[start:]:
        collected.append(text)
        depth += text.count("{") - text.count("}")
        seen = seen or "{" in text
        if seen and depth <= 0:
            break
    return collected


def _indented_block(lines: list[str], start: int) -> list[str]:
    indent = len(lines[start]) - len(lines[start].lstrip())
    collected = [lines[start]]
    for text in lines[start + 1 :]:
        if text.strip() and len(text) - len(text.lstrip()) <= indent and not text.lstrip().startswith((")", "]")):
            break
        collected.append(text)
    return collected


def normalized_function_text(path: Path, line: int, name: str) -> str | None:
    """The whitespace-normalized text of ``name`` near ``line``, or ``None``."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    start = _declaration_start(lines, line if 1 <= line <= len(lines) else 1, _declaration(path, name))
    if start is None:
        return None
    block = _indented_block(lines, start) if path.suffix in {".py", ".pyi"} else _brace_block(lines, start)
    return re.sub(r"\s+", " ", "\n".join(block)).strip()


def digest_of(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def function_exists(path: Path, name: str) -> bool:
    """Whether ``name`` is still declared in ``path``."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return any(_declaration(path, name).search(line) for line in source.splitlines())


def delegates_to(path: Path, line: int, names: tuple[str, str]) -> bool:
    """Whether function ``names[0]`` merely CALLS ``names[1]`` (one implementation)."""
    name, other = names
    if name == other:
        return False
    body = normalized_function_text(path, line, name)
    return body is not None and re.search(rf"\b{re.escape(other)}\s*\(", body) is not None
