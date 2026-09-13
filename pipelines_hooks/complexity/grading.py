"""Grade one measured row: the exhaustive-dispatch verdict and its residual.

Split out of :mod:`pipelines_hooks.complexity.judge` (which keeps the
before/after comparison), so each module holds one focused responsibility:
this one turns a raw ``cccc`` row into a judged ``Graded`` row, ``judge.py``
compares two sets of already-graded rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from pipelines_hooks.complexity import MAX_COGNITIVE, MAX_CYCLOMATIC
from pipelines_hooks.complexity.cccc import Row
from pipelines_hooks.rust.dispatch import dispatch_shape, exhaustive_dispatch_exempt

CAPS = (MAX_CYCLOMATIC, MAX_COGNITIVE)


class Graded(NamedTuple):
    """One measured row plus the exhaustive-dispatch verdict for its source.

    ``exempt`` and ``residual`` are recomputed from the source under
    measurement on every run, never persisted. ``residual`` (measured
    cyclomatic minus match-arm count) is set only when ``exempt`` is True; a
    non-exempt row is judged on its raw cyclomatic and has no discounted
    quantity.
    """

    cyclomatic: int
    cognitive: int
    exempt: bool
    residual: int | None = None

    @property
    def effective_cyclomatic(self) -> int:
        """The cyclomatic value this gate compares between two rows.

        Raw for a non-exempt row. For an accepted exhaustive dispatcher, the
        residual, so growth purely from added match arms does not register,
        while any other growth still does. Never zeroed.
        """
        return self.residual if self.exempt and self.residual is not None else self.cyclomatic

    def _cyclomatic_over_cap(self) -> bool:
        """Raw cyclomatic over cap -- discounted to False when exempt, since
        the exemption exists precisely to accept that axis for this row."""
        return self.cyclomatic > MAX_CYCLOMATIC and not self.exempt

    def over_cap(self) -> bool:
        """True on this row's own terms, independent of any history."""
        return self._cyclomatic_over_cap() or self.cognitive > MAX_COGNITIVE


def rust_source(path: Path) -> str | None:
    """The Rust text of a measured file, or ``None`` when the rule cannot apply."""
    if path.suffix.lower() != ".rs":
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _residual(source: str | None, row: Row) -> int | None:
    """Cyclomatic minus match-arm count, for a row already known exempt.

    ``exhaustive_dispatch_exempt`` already proved ``dispatch_shape`` returns a
    usable shape with at least one arm for this row -- one of its four
    conditions -- so a ``None`` or zero-arm shape here fails closed (no
    residual) rather than dividing by an assumption.
    """
    shape = dispatch_shape(source, row.line) if source is not None else None
    if shape is None or shape.arms <= 0:
        return None
    return row.cyclomatic - shape.arms


def _grade_row(row: Row, source: str | None) -> Graded:
    metrics = (row.cyclomatic, row.cognitive)
    exempt = exhaustive_dispatch_exempt(source, line=row.line, metrics=metrics, caps=CAPS)
    residual = _residual(source, row) if exempt else None
    return Graded(row.cyclomatic, row.cognitive, exempt, residual)


def grade(rows: list[Row], source: str | None) -> dict[str, list[Graded]]:
    """``{qualified name: [Graded, ...]}``; names collide, so values are lists."""
    graded: dict[str, list[Graded]] = {}
    for row in rows:
        graded.setdefault(row.name, []).append(_grade_row(row, source))
    return graded
