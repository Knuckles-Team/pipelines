"""Findings and the per-file context their rules are evaluated in."""

from __future__ import annotations

import re
from dataclasses import dataclass

CONTAINER_DIGEST_RE = re.compile(r"@sha256:[0-9a-fA-F]{64}(?:$|\s)")
NETWORK_TO_SHELL_RE = re.compile(r"(?:curl|wget)\b[^\n|]*\|\s*(?:/bin/)?(?:ba|z|k)?sh\b", re.IGNORECASE)


@dataclass(frozen=True, order=True)
class Finding:
    repository: str
    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        location = f"{self.repository}/{self.path}" + (f":{self.line}" if self.line else "")
        return f"{location}: {self.rule}: {self.message}"


@dataclass(frozen=True)
class Source:
    """One inspected file: repository label, display path and text."""

    label: str
    display: str
    text: str

    def line_of(self, offset: int) -> int:
        return self.text.count("\n", 0, offset) + 1

    def at_line(self, line: int, *, rule: str, message: str) -> Finding:
        return Finding(self.label, self.display, line, rule, message)

    def at_offset(self, offset: int, *, rule: str, message: str) -> Finding:
        return self.at_line(self.line_of(offset), rule=rule, message=message)

    def each_match(self, pattern: re.Pattern[str], *, rule: str, message: str) -> list[Finding]:
        return [self.at_offset(m.start(), rule=rule, message=message) for m in pattern.finditer(self.text)]


def pinned_digest(image: str) -> bool:
    return bool(CONTAINER_DIGEST_RE.search(image + " "))
