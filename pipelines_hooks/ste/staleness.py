"""Staleness claims: patterns that detect ownership claims no longer true.

Each pattern carries the fix message to display. Patterns come from the
consumer's configuration table plus the (empty) fleet-wide default, so the
bundled gate ships no opinion about any one repository's ownership.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.ste.scan import Finding


@dataclass(frozen=True)
class StalePattern:
    """One pattern plus the message its hit reports."""

    pattern: str
    message: str


def _compile(table: Sequence[StalePattern]) -> list[tuple[StalePattern, re.Pattern[str]]]:
    compiled: list[tuple[StalePattern, re.Pattern[str]]] = []
    for pattern in table:
        try:
            compiled.append((pattern, re.compile(pattern.pattern)))
        except re.error as exc:
            raise CannotRun(f"ste staleness pattern does not compile ({pattern.pattern}): {exc}") from exc
    return compiled


def check_lines(path: str, lines: Sequence[tuple[int, str]], table: Sequence[StalePattern]) -> list[Finding]:
    """Staleness findings over numbered lines."""
    compiled = _compile(table)
    findings: list[Finding] = []
    for number, text in lines:
        for pattern, regex in compiled:
            if regex.search(text):
                findings.append(Finding("T", path, number, pattern.message))
    return findings
