"""Judge NEW / WORSE findings by comparing already-graded rows against HEAD.

The staged gate is diff-scoped and deliberately NOT a baseline: nothing is
written, no count is frozen, and the real numbers of every touched file are
printed on every run. Its rule:

* a function absent from HEAD and over either cap            -> FAIL (NEW)
* a function present in HEAD whose worst value rose           -> FAIL (WORSE)
* an over-cap row ADDED under a name that already existed     -> FAIL (NEW)
* a pre-existing over-cap function left unchanged             -> pass

EXEMPTION STATUS IS NOT PART OF THE COMPARED VALUE. BUG-CX-EXEMPT-SCORE: an
earlier version hard-zeroed an exempt row's cyclomatic before the before/after
comparison ran, which folded EXEMPTION STATUS into the METRIC being compared.
A function that started exempt-over-cap (zeroed to 0) and was simplified below
the cap -- ceasing to need the exemption at all, since
``exhaustive_dispatch_exempt`` never grants it to an at-or-under-cap function
-- read as its full raw value appearing from nowhere (0 -> 9), which the
comparison called a regression. Simplifying a function until it no longer
needed the exemption was, perversely, the one thing this gate could not tell
from making it worse.

The fix (in :mod:`pipelines_hooks.complexity.grading`) compares RAW metrics on
both sides and treats exemption as a classifier, not a rewrite of the number
being classified:

* a function over a cap and NOT exempt on the new side always fails, new or
  pre-existing -- the ordinary case;
* a function that was over a cap and exempt at base, and is at-or-under the
  cap on the new side (so no longer exempt -- the rule never exempts an
  at-or-under-cap function), always passes: this is the transition the
  exemption exists to allow;
* an exempt function's cyclomatic axis is judged on its RESIDUAL (measured
  cyclomatic minus its match-arm count), not zeroed. Adding arms leaves the
  residual alone -- the whole point of keeping the match exhaustive is that
  arms are free -- so that alone never reads as a regression. Any other
  growth raises the residual and fails like ordinary debt would. Cognitive
  complexity is never graded and never exempt on either side.
"""

from __future__ import annotations

from typing import NamedTuple

from pipelines_hooks.complexity import MAX_COGNITIVE, MAX_CYCLOMATIC
from pipelines_hooks.complexity.grading import Graded, grade, rust_source

__all__ = ["Finding", "Graded", "file_summary", "grade", "judge", "rust_source"]


class Finding(NamedTuple):
    kind: str
    name: str
    before: tuple[int, int]
    after: tuple[int, int]


def _worst_cognitive(rows: list[Graded]) -> int:
    return max(r.cognitive for r in rows)


def _worst_raw_cyclomatic(rows: list[Graded]) -> Graded:
    """The row with the worst RAW cyclomatic value -- raw, not effective, so
    the selection itself is never already discounted by exemption."""
    return max(rows, key=lambda r: r.cyclomatic)


def _cyclomatic_regressed(prior: list[Graded], rows: list[Graded]) -> tuple[bool, int, int]:
    """Whether the cyclomatic axis regressed, plus the raw (before, after).

    One case bypasses the effective-value comparison entirely: the row was
    exempt-over-cap at base and is at-or-under the cap now (so necessarily not
    exempt -- the rule never exempts an at-or-under-cap function). That
    transition is the one the exemption exists to allow, and always passes.
    Otherwise, compare ``effective_cyclomatic`` on both sides.
    """
    before = _worst_raw_cyclomatic(prior)
    after = _worst_raw_cyclomatic(rows)
    if before.exempt and after.cyclomatic <= MAX_CYCLOMATIC:
        return False, before.cyclomatic, after.cyclomatic
    return after.effective_cyclomatic > before.effective_cyclomatic, before.cyclomatic, after.cyclomatic


def _added_over_cap(name: str, prior: list[Graded], rows: list[Graded]) -> list[Finding]:
    """Over-cap rows ADDED to a name that already existed in HEAD.

    A new row below an older worst row must not disappear behind it, so the
    multiplicity of over-cap rows is compared as well as the worst value. A
    row crossing a cap without any row being ADDED is a worsening of an
    existing row instead, which ``_cyclomatic_regressed``/``_worst_cognitive``
    report -- counting it here too would report one function twice.
    """
    prior_count = sum(row.over_cap() for row in prior)
    after = sorted((row for row in rows if row.over_cap()), key=lambda r: (r.cyclomatic, r.cognitive))
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
        cyc_regressed, cyc_before, cyc_after = _cyclomatic_regressed(prior, rows)
        cog_before, cog_after = _worst_cognitive(prior), _worst_cognitive(rows)
        if cyc_regressed or cog_after > cog_before:
            findings.append(Finding("WORSE", name, (cyc_before, cog_before), (cyc_after, cog_after)))
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
