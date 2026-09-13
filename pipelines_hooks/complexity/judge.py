"""Grade measured rows and judge NEW / WORSE findings against HEAD.

The staged gate is diff-scoped and deliberately NOT a baseline: nothing is
written, no count is frozen, and the real numbers of every touched file are
printed on every run. Its rule:

* a function absent from HEAD and over either cap            -> FAIL (NEW)
* a function present in HEAD whose worst value rose           -> FAIL (WORSE)
* an over-cap row ADDED under a name that already existed     -> FAIL (NEW)
* a pre-existing over-cap function left unchanged             -> pass
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from pipelines_hooks.complexity import MAX_COGNITIVE, MAX_CYCLOMATIC
from pipelines_hooks.complexity.cccc import Row
from pipelines_hooks.rust.dispatch import exhaustive_dispatch_exempt

CAPS = (MAX_CYCLOMATIC, MAX_COGNITIVE)


class Graded(NamedTuple):
    """One measured row plus the exhaustive-dispatch verdict for its source."""

    cyclomatic: int
    cognitive: int
    exempt: bool

    @property
    def judged_cyclomatic(self) -> int:
        """Zero for an accepted exhaustive dispatcher; its raw value otherwise."""
        return 0 if self.exempt else self.cyclomatic

    def over_cap(self) -> bool:
        return self.judged_cyclomatic > MAX_CYCLOMATIC or self.cognitive > MAX_COGNITIVE


class Finding(NamedTuple):
    kind: str
    name: str
    before: tuple[int, int]
    after: tuple[int, int]


def rust_source(path: Path) -> str | None:
    """The Rust text of a measured file, or ``None`` when the rule cannot apply."""
    if path.suffix.lower() != ".rs":
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def grade(rows: list[Row], source: str | None) -> dict[str, list[Graded]]:
    """``{qualified name: [Graded, ...]}``; names collide, so values are lists."""
    graded: dict[str, list[Graded]] = {}
    for row in rows:
        metrics = (row.cyclomatic, row.cognitive)
        exempt = exhaustive_dispatch_exempt(source, line=row.line, metrics=metrics, caps=CAPS)
        graded.setdefault(row.name, []).append(Graded(row.cyclomatic, row.cognitive, exempt))
    return graded


def _worst(rows: list[Graded]) -> tuple[int, int]:
    return max(r.judged_cyclomatic for r in rows), max(r.cognitive for r in rows)


def _added_over_cap(name: str, prior: list[Graded], rows: list[Graded]) -> list[Finding]:
    """Over-cap rows ADDED to a name that already existed in HEAD.

    A new row below an older worst row must not disappear behind it, so the
    multiplicity of over-cap rows is compared as well as the worst value.
    """
    prior_count = sum(row.over_cap() for row in prior)
    after = sorted((row for row in rows if row.over_cap()), key=lambda r: (r.judged_cyclomatic, r.cognitive))
    added = min(len(after) - prior_count, len(rows) - len(prior))
    return [Finding("NEW", name, (0, 0), (r.cyclomatic, r.cognitive)) for r in after[: max(added, 0)]]


def judge(before: dict[str, list[Graded]], after: dict[str, list[Graded]]) -> list[Finding]:
    """Every NEW and WORSE finding; empty means clean."""
    findings: list[Finding] = []
    for name, rows in sorted(after.items()):
        prior = before.get(name)
        if prior is None:
            findings.extend(
                Finding("NEW", name, (0, 0), (r.cyclomatic, r.cognitive)) for r in rows if r.over_cap()
            )
            continue
        findings.extend(_added_over_cap(name, prior, rows))
        if _worst(rows)[0] > _worst(prior)[0] or _worst(rows)[1] > _worst(prior)[1]:
            findings.append(Finding("WORSE", name, _worst(prior), _worst(rows)))
    return findings


def file_summary(rel: str, graded: dict[str, list[Graded]]) -> str | None:
    """The real absolute numbers of one touched file (raw, never graded)."""
    flat = [row for rows in graded.values() for row in rows]
    if not flat:
        return None
    raw_over = sum(r.cyclomatic > MAX_CYCLOMATIC or r.cognitive > MAX_COGNITIVE for r in flat)
    accepted = sum(r.exempt for r in flat)
    note = f", {accepted} accepted as exhaustive dispatch" if accepted else ""
    return (
        f"  {rel}: {len(flat)} fn, worst cyc {max(r.cyclomatic for r in flat)}, worst cog "
        f"{max(r.cognitive for r in flat)}, {raw_over} already over "
        f"{MAX_CYCLOMATIC}/{MAX_COGNITIVE}{note}"
    )
