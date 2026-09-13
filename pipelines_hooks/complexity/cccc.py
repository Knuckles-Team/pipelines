"""Run cccc 1.6.0 and validate its JSON report, failing closed on any drift."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env

#: Canonical names of cccc 1.6.0's compiled-in language registry.
LANGUAGES = (
    "es", "rust", "go", "php", "ruby", "scheme", "commonlisp", "emacslisp",
    "clojure", "kotlin", "python", "zig", "c", "perl", "swift", "java", "dart",
)
#: The union of every adapter's default extensions. A file outside this set is
#: never handed to cccc, so an unsupported type cannot look like "0 functions".
SUPPORTED_SUFFIXES = frozenset(
    ".c .cl .clj .cljs .cljc .dart .el .h .java .js .jsx .kt .kts .lisp .lsp "
    ".mjs .mts .php .pl .pm .py .pyi .rb .rkt .rktd .rktl .rs .scm .sld .ss "
    ".swift .t .ts .tsx .cjs .zig".split()
)


class Row(NamedTuple):
    """One measured function."""

    name: str
    cyclomatic: int
    cognitive: int
    line: int


def run(executable: str, paths: list[str], *, cwd: Path) -> dict[str, Any]:
    """The validated report for ``paths`` (one or many files)."""
    command = [executable, "--no-config", "--min", "0", "--lang", ",".join(LANGUAGES), *paths]
    try:
        result = subprocess.run(
            command, cwd=str(cwd), env=sanitized_env(), capture_output=True, text=True,
            timeout=900, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"could not run cccc: {exc}") from exc
    if result.returncode != 0 or not (result.stdout or "").strip():
        raise CannotRun(f"cccc exited {result.returncode}: {(result.stderr or '').strip()[:300]}")
    return validated_document(result.stdout)


def validated_document(raw: str) -> dict[str, Any]:
    """Parse a report and reject parse errors or a malformed shape."""
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CannotRun(f"cccc output is not JSON: {exc}") from exc
    summary = document.get("summary") if isinstance(document, dict) else None
    count = summary.get("parse_error_count") if isinstance(summary, dict) else None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise CannotRun("cccc report has no valid summary.parse_error_count")
    if count:
        raise CannotRun(f"cccc reported {count} parse error(s)")
    files = document.get("files")
    if not isinstance(files, list) or not files:
        raise CannotRun("cccc report has no files array")
    return document


def _row(function: object, prefix: str) -> tuple[Row, list[Any]]:
    if not isinstance(function, dict) or not isinstance(function.get("name"), str):
        raise CannotRun("cccc returned a function without a valid name")
    values = [function.get(field) for field in ("cyclomatic", "cognitive", "line")]
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
        raise CannotRun(f"cccc function {function['name']!r} has invalid metrics")
    children = function.get("children", [])
    if not isinstance(children, list):
        raise CannotRun(f"cccc function {function['name']!r} has invalid children")
    return Row(f"{prefix}{function['name']}", *values), children


def _walk(functions: list[Any], prefix: str) -> Iterator[Row]:
    for function in functions:
        row, children = _row(function, prefix)
        yield row
        yield from _walk(children, f"{row.name}.")


def file_rows(document: dict[str, Any]) -> Iterator[tuple[str, Row]]:
    """``(path, row)`` for every function and nested child in a report.

    A qualified name is NOT unique (two classes may each define ``submit``),
    so callers keep every row rather than a name-keyed pair.
    """
    for entry in document["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise CannotRun("cccc report contains a file without a path")
        functions = entry.get("functions")
        if not isinstance(functions, list) or entry.get("parse_errors"):
            raise CannotRun(f"cccc could not measure {entry['path']}")
        for row in _walk(functions, ""):
            yield entry["path"], row
