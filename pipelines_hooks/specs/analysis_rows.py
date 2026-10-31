"""Raw text of the active leaf rows of a ``requirements.md``."""

from __future__ import annotations

from pipelines_hooks.specs.analysis import active_leaf_rows
from pipelines_hooks.specs.narrative import FIRST_CELL_RE
from pipelines_hooks.specs.requirements_doc import parse_rows


def leaf_row_texts(requirements: str) -> list[tuple[str, str]]:
    """``(row ID, full row line)`` of every active row that is not a rollup parent."""
    leaves = {r.id for r in active_leaf_rows(parse_rows(requirements))}
    out = []
    for line in requirements.splitlines():
        match = FIRST_CELL_RE.match(line)
        if match and match.group(1) in leaves:
            out.append((match.group(1), line))
    return out
