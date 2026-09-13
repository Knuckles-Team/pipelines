"""Parse KISS reports and narrow them to the findings a staged diff caused.

* A rule inside one function body counts only when the enclosing function is
  NEW (no same-named function at HEAD) or MODIFIED (its exact source text
  differs from the same-ordinal function at HEAD). Content, not line numbers or
  bare names, decides: extraction shifts both without changing meaning.
* A rule that aggregates a whole file or a whole type (:data:`AGGREGATE_RULES`)
  counts when newly crossed or when the reported count grew.

A finding whose enclosing function cannot be located counts (fail closed). No
baseline and no stored number: both reports are computed fresh on each run.
"""

from __future__ import annotations

import re
from collections.abc import Callable

VIOLATION_RE = re.compile(
    r"^VIOLATION:(?P<rule>[^:]+):(?P<path>[^:]*):(?P<line>\d+):(?P<name>[^:]*):\s?(?P<message>.*)$"
)
AGGREGATE_RULES = frozenset(
    {
        "statements_per_file",
        "lines_per_file",
        "functions_per_file",
        "interface_types_per_file",
        "concrete_types_per_file",
        "imported_names_per_file",
        "methods_per_class",
    }
)
_INT_RE = re.compile(r"\d+")
Violation = dict[str, str]
SpanFinder = Callable[[str, str], list[tuple[int, int, str]]]


def parse_report(text: str | None) -> list[Violation]:
    """The ``VIOLATION:`` lines of a KISS report."""
    return [m.groupdict() for line in (text or "").splitlines() if (m := VIOLATION_RE.match(line))]


def format_violation(violation: Violation) -> str:
    """A violation rendered back into KISS's report line format."""
    return (
        f"VIOLATION:{violation['rule']}:{violation['path']}:{violation['line']}:"
        f"{violation['name']}: {violation['message']}"
    )


def _magnitude(message: str) -> int | None:
    match = _INT_RE.search(message)
    return int(match.group()) if match else None


def _head_magnitudes(head: list[Violation]) -> dict[tuple[str, str], int]:
    magnitudes: dict[tuple[str, str], int] = {}
    for violation in head:
        value = _magnitude(violation["message"])
        if violation["rule"] in AGGREGATE_RULES and value is not None:
            key = (violation["rule"], violation["name"])
            magnitudes[key] = max(magnitudes.get(key, -1), value)
    return magnitudes


def _aggregate_attributable(violation: Violation, head: dict[tuple[str, str], int]) -> bool:
    before = head.get((violation["rule"], violation["name"]))
    after = _magnitude(violation["message"])
    return before is None or (after is not None and after > before)


def _item_attributable(violation: Violation, sources: tuple[str, str], spans: SpanFinder) -> bool:
    staged_source, head_source = sources
    staged = spans(staged_source, violation["name"])
    line = int(violation["line"])
    ordinal = next((i for i, (start, end, _) in enumerate(staged) if start <= line <= end), None)
    if ordinal is None:
        return True
    head = spans(head_source, violation["name"])
    return ordinal >= len(head) or head[ordinal][2] != staged[ordinal][2]


def attributable(
    staged: tuple[str, str], head: tuple[str, str] | None, spans: SpanFinder
) -> list[Violation]:
    """The staged findings the diff caused. ``staged``/``head`` are (source, report).

    ``head`` is ``None`` for a file with no HEAD blob: every finding counts.
    """
    violations = parse_report(staged[1])
    if head is None:
        return violations
    magnitudes = _head_magnitudes(parse_report(head[1]))
    return [
        violation
        for violation in violations
        if (
            _aggregate_attributable(violation, magnitudes)
            if violation["rule"] in AGGREGATE_RULES
            else _item_attributable(violation, (staged[0], head[0]), spans)
        )
    ]
