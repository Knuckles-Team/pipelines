"""spec-standard: every requirement row states its prerequisites with a ``Depends:`` line.

A row carries ``Depends: <row ID>, <row ID>.`` or ``Depends: none.``. A listed ID must resolve to a row, and the
rows of one repository must not depend on each other in a cycle. A row without the line is a warning until
``REQUIRED_FROM``, then an error. See reference/spec-standard.md "Row dependencies".
"""

from __future__ import annotations

import re
from datetime import date

from pipelines_hooks.specs.requirements_doc import parse_rows

#: From this date a row without a ``Depends:`` line is an error instead of a warning.
REQUIRED_FROM = date(2027, 1, 1)
#: Marks the findings that only warn today.
WARNING_MARK = " (warning: error from " + REQUIRED_FROM.isoformat() + ")"

_LINE_RE = re.compile(r"\bDepends:")
_ROW_RE = re.compile(r"^\|\s*`?([A-Z][A-Z0-9-]*-R\d{2,3}(?:\.\d+)*)`?\s*\|")


def _spec_prefix(row_id: str) -> str:
    return re.sub(r"(?:-R\d{2,3})(?:\.\d+)*$", "", row_id)


def _lacking_line(text: str, active: set[str]) -> list[str]:
    out = []
    for line in text.splitlines():
        match = _ROW_RE.match(line)
        if match and match.group(1) in active and not _LINE_RE.search(line):
            out.append(match.group(1))
    return list(dict.fromkeys(out))


def _cycles(graph: dict[str, tuple[str, ...]]) -> list[list[str]]:
    """Every distinct dependency cycle, each as the rows along it (first row repeated at the end)."""
    found: list[list[str]] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, ()):
            if state.get(dep) == 1:
                found.append([*stack[stack.index(dep) :], dep])
            elif dep in graph and dep not in state:
                visit(dep)
        stack.pop()
        state[node] = 2

    for node in graph:
        if node not in state:
            visit(node)
    return found


def check_dependencies(
    specs: dict[str, str],
    today: date | None = None,
    foreign: set[str] | None = None,
) -> list[tuple[str, str]]:
    """``(spec directory, finding)`` for the requirements of every spec of one repository.

    ``specs`` maps a spec directory name to its ``requirements.md`` text. ``foreign`` holds the row IDs other
    repositories define; without it an ID of another repository cannot be checked and is accepted.
    """
    today = today or date.today()
    rows = {name: parse_rows(text) for name, text in specs.items()}
    active = {r.id for rs in rows.values() for r in rs if r.retired_reason is None}
    local_prefixes = {_spec_prefix(i) for i in active}
    out: list[tuple[str, str]] = []
    graph: dict[str, tuple[str, ...]] = {}
    owner: dict[str, str] = {}
    for name, rs in rows.items():
        for row in rs:
            if row.retired_reason is not None:
                continue
            graph[row.id] = row.depends_on
            owner[row.id] = name
            for dep in row.depends_on:
                local = _spec_prefix(dep) in local_prefixes
                if dep not in active and (local or foreign is not None and dep not in foreign):
                    out.append((name, f"{row.id} depends on {dep}, which no row defines; give it a row first"))
    for cycle in _cycles({k: tuple(d for d in v if d in graph) for k, v in graph.items()}):
        out.append((owner[cycle[0]], "dependency cycle: " + " -> ".join(cycle)))
    for name, text in specs.items():
        missing = _lacking_line(text, {r.id for r in rows[name] if r.retired_reason is None})
        if not missing:
            continue
        shown = ", ".join(missing[:3]) + (f" and {len(missing) - 3} more" if len(missing) > 3 else "")
        if today >= REQUIRED_FROM:
            out += [
                (name, f"{i} has no 'Depends:' line; list prerequisite row IDs or 'Depends: none'") for i in missing
            ]
        else:
            out.append((name, f"{len(missing)} row(s) have no 'Depends:' line ({shown}){WARNING_MARK}"))
    return out
