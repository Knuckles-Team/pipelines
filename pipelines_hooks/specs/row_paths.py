"""A spec row names a repository path that exists, or marks it planned.

Scans ``requirements.md`` and ``test-spec.md`` of one spec directory for backticked repository
paths (a trailing ``:line`` or ``::test`` is stripped). A path whose first segment is a top-level
directory of the repository and whose last segment has an extension must exist. A path is not
checked when the bullet or table row that names it marks it planned: ``(planned``, ``(new``,
``planned``, ``does not exist yet``, ``to be created`` or ``owning change adds``.
Failure scoping (a row the change adds fails, any other row is advisory) lives in ``standard.py``.
See reference/spec-standard.md "Consistency analysis".
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re

from pipelines_hooks.specs.narrative import ROW_TOKEN_RE

FILES = ("requirements.md", "test-spec.md")
PATH_RE = re.compile(r"`((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_-]+\.[A-Za-z0-9]+)(?::\d+)?(?:::[A-Za-z0-9_:]+)?`")
PLANNED_RE = re.compile(
    r"\(planned|\(new\b|\bplanned\b|does not exist yet|not yet (?:exist|land|written)|to be created|owning change adds",
    re.I,
)
_START = ("- ", "| ", "#")


def _blocks(lines: list[str]) -> list[tuple[int, int]]:
    """Half-open line ranges of each bullet or table row with its continuation lines."""
    out, begin = [], 0
    while begin < len(lines):
        end = begin + 1
        while end < len(lines) and lines[end].strip() and not lines[end].startswith(_START):
            end += 1
        out.append((begin, end))
        begin = end
    return out


def check_row_paths(root: Path, texts: Mapping[str, str]) -> list[str]:
    """One finding per named path that is missing and not planned, carrying the row ID when the row has one."""
    tops = {p.name for p in root.iterdir() if p.is_dir()} if root.is_dir() else set()
    out: list[str] = []
    for name in FILES:
        lines = texts.get(name, "").split("\n")
        for begin, end in _blocks(lines):
            block = "\n".join(lines[begin:end])
            if PLANNED_RE.search(block):
                continue
            row = ROW_TOKEN_RE.search(block)
            for offset, line in enumerate(lines[begin:end]):
                for hit in PATH_RE.finditer(line):
                    path = hit.group(1)
                    if path.split("/", 1)[0] in tops and not (root / path).exists():
                        who = f" row {row.group(1)}" if row else ""
                        out.append(
                            f"{name}:{begin + offset + 1}:{who} names missing file {path}; name the current file or mark it planned"
                        )
    return out
