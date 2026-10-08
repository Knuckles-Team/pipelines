"""User-facing CLI strings: argparse ``help``, ``description``, ``epilog``.

Only the wordlist rules apply here (banned, modals, fuzzy, person); sentence
shape is measured on document prose, not on CLI labels.
"""

from __future__ import annotations

import re

from pipelines_hooks.ste.scan import Finding, _CLI_TIERS, line_findings
from pipelines_hooks.ste.words import Wordlist

_CLI_STRING = re.compile(
    r"\b(help|description|epilog)\s*=\s*"
    r"(?:\"\"\"(?P<td>(?:(?!\"\"\").)*)\"\"\""
    r"|'''(?P<ts>(?:(?!''').)*)'''"
    r"|\"(?P<dq>(?:\\.|[^\"\\])*)\""
    r"|'(?P<sq>(?:\\.|[^'\\])*)')",
    re.S,
)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _literal(match: re.Match[str]) -> tuple[int, str]:
    start = match.start()
    content = next(group for group in match.groups()[1:] if group is not None)
    for index in range(2, 6):
        begin, _ = match.span(index)
        if begin != -1:
            start = begin
            break
    return start, content


def _cli_line(text: str, *, number: int, wordlist: Wordlist, path: str) -> list[Finding]:
    stripped = text.strip()
    if not stripped:
        return []
    return line_findings(stripped, path=path, number=number, wordlist=wordlist, tiers=_CLI_TIERS)


def cli_findings(text: str, wordlist: Wordlist, *, path: str) -> list[Finding]:
    """Wordlist findings inside argparse strings in one source file."""
    findings: list[Finding] = []
    for match in _CLI_STRING.finditer(text):
        start, literal = _literal(match)
        position = start
        for chunk in literal.splitlines(keepends=True):
            findings.extend(_cli_line(chunk.rstrip("\n"), number=_line_of(text, position), wordlist=wordlist, path=path))
            position += len(chunk)
    return findings
