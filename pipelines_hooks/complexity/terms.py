"""Split over-cap functions by the terms of acceptance: accepted vs real backlog.

A census that prints one undifferentiated number is noise. This applies the
identical rule the staged gate applies (:mod:`pipelines_hooks.rust.dispatch`)
so the census and the hook can never disagree about what is accepted.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pipelines_hooks.complexity import MAX_COGNITIVE, MAX_CYCLOMATIC
from pipelines_hooks.complexity.cccc import Row
from pipelines_hooks.rust.dispatch import dispatch_shape

#: Every disposition of a cyclomatic-only over-cap function, in report order.
DISPOSITIONS = (
    ("accepted", "exhaustive dispatch, residual within cap -- ACCEPTED BY RULE"),
    ("catch_all", "has a catch-all arm, so the match is NOT exhaustive"),
    ("no_match", "no `match` in the body: branching that is not dispatch"),
    ("residual", "dispatch discounted, the rest still exceeds the cap"),
    ("unattributable", "arm count exceeds cyclomatic: attribution unproven"),
    ("not_rust", "not Rust: rustc exhaustiveness does not apply"),
    ("unreadable", "source could not be lexed or located"),
)


def _source(path: Path, cache: dict[Path, str | None]) -> str | None:
    if path not in cache:
        try:
            cache[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            cache[path] = None
    return cache[path]


def classify(path: Path, row: Row, cache: dict[Path, str | None]) -> str:
    """The disposition the terms give one cyclomatic-only over-cap function."""
    if path.suffix.lower() != ".rs":
        return "not_rust"
    source = _source(path, cache)
    shape = None if source is None else dispatch_shape(source, row.line)
    if shape is None:
        return "unreadable"
    if shape.arms == 0 or shape.catch_alls:
        return "no_match" if shape.arms == 0 else "catch_all"
    residual = row.cyclomatic - shape.arms
    if residual < 1:
        return "unattributable"
    return "accepted" if residual <= MAX_CYCLOMATIC else "residual"


def tally(rows: list[tuple[Path, Row]]) -> tuple[list[tuple[Path, Row]], int, Counter[str]]:
    """``(over-cap rows, cognitive-over count, disposition tally)``."""
    over = [(p, r) for p, r in rows if r.cyclomatic > MAX_CYCLOMATIC or r.cognitive > MAX_COGNITIVE]
    cognitive = [(p, r) for p, r in over if r.cognitive > MAX_COGNITIVE]
    cache: dict[Path, str | None] = {}
    counts = Counter(classify(p, r, cache) for p, r in over if r.cognitive <= MAX_COGNITIVE)
    return over, len(cognitive), counts


def unaccepted(over: list[tuple[Path, Row]]) -> list[tuple[Path, Row]]:
    """Over-cap rows the terms do not accept: the real backlog, row by row."""
    cache: dict[Path, str | None] = {}
    return [
        (path, row)
        for path, row in over
        if row.cognitive > MAX_COGNITIVE or classify(path, row, cache) != "accepted"
    ]


def report(measured: int, over: int, *, cognitive: int, counts: Counter[str]) -> int:
    """Print the split and return the real backlog."""
    backlog = over - counts["accepted"]
    print(
        f"complexity terms: {measured} function(s) measured, {over} over cyclomatic "
        f"{MAX_CYCLOMATIC} or cognitive {MAX_COGNITIVE}"
    )
    print(f"  cognitive over cap        {cognitive:5d}  genuinely complex -- never accepted")
    for key, why in DISPOSITIONS:
        print(f"  {key:<25} {counts[key]:5d}  {why}")
    print(f"  ACCEPTED BY RULE          {counts['accepted']:5d}")
    print(f"  REAL BACKLOG              {backlog:5d}")
    return backlog
