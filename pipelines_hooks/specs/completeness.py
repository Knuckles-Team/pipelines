"""spec-standard: a behaviour row holds enough text to implement without assumptions.

Each active leaf row names its production caller chain (``Caller chain:``), one ``Shape:``
sentence (files, types and the existing helper to reuse), and a served test as ``path::name``.
No row says TBD. A rollup parent is covered by its child rows. See reference/spec-standard.md
"Complete rows".
"""

from __future__ import annotations

import re

from pipelines_hooks.specs.analysis_rows import leaf_row_texts

CALLER_RE = re.compile(r"\bCaller chain:")
SHAPE_RE = re.compile(r"\bShape:")
TEST_RE = re.compile(r"[\w./-]+::\w+")
TBD_RE = re.compile(r"\bTBD\b")
CHECKS = (
    (CALLER_RE, "a 'Caller chain:' sentence from the entry point to the new code"),
    (SHAPE_RE, "a 'Shape:' sentence naming the files, types and the helper to reuse"),
    (TEST_RE, "a test as path::name"),
)


def check_complete_rows(requirements: str) -> list[str]:
    """One finding per missing element of a behaviour row, and per TBD."""
    out = []
    for row_id, text in leaf_row_texts(requirements):
        out += [f"{row_id} behaviour row lacks {what}" for pattern, what in CHECKS if not pattern.search(text)]
        if TBD_RE.search(text):
            out.append(f"{row_id} behaviour row says TBD; state the value")
    return out
