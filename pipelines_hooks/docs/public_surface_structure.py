"""Ordered README section contract and quick-start extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pipelines_hooks.docs.public_surface_constants import HEADING_RE, README_HEADINGS


def _normalized_heading(match: re.Match[str]) -> str:
    return re.sub(r"\s+", " ", match.group(2).strip(" #\t").lower())


def _fence(line: str) -> tuple[str, int] | None:
    match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
    if not match:
        return None
    marker = match.group(1)
    return marker[0], len(marker)


@dataclass
class _SectionAccumulator:
    rows: list[tuple[str, str]] = field(default_factory=list)
    name: str | None = None
    body: list[str] = field(default_factory=list)
    fence_char: str = ""
    fence_size: int = 0

    def consume(self, line: str) -> None:
        """Accumulate a line, treating headings inside fenced blocks as text."""
        if self._consume_fence(line):
            self._append(line)
            return
        heading = HEADING_RE.match(line) if not self.fence_char else None
        if heading and len(heading.group(1)) == 2:
            self._finish_section()
            self.name = _normalized_heading(heading)
            return
        self._append(line)

    def _consume_fence(self, line: str) -> bool:
        fence = _fence(line)
        if not fence:
            return False
        char, size = fence
        if not self.fence_char:
            self.fence_char, self.fence_size = char, size
        elif char == self.fence_char and size >= self.fence_size:
            self.fence_char, self.fence_size = "", 0
        return True

    def _append(self, line: str) -> None:
        if self.name is not None:
            self.body.append(line)

    def _finish_section(self) -> None:
        if self.name is not None:
            self.rows.append((self.name, "\n".join(self.body)))
        self.body = []

    def finish(self) -> list[tuple[str, str]]:
        """Return accumulated sections, including the final open section."""
        self._finish_section()
        return self.rows


def sections(text: str) -> list[tuple[str, str]]:
    """Return level-two headings with body text, excluding fenced examples."""
    parser = _SectionAccumulator()
    for line in text.splitlines():
        parser.consume(line)
    return parser.finish()


def flow_findings(text: str) -> list[str]:
    """Require the exact ordered H2 flow and disallow a separate installation section."""
    actual = [heading for heading, _ in sections(text)]
    if "installation" in actual:
        return [
            "README.md must not have a separate Installation section; put the minimal install/run path in Quick start"
        ]
    if actual != list(README_HEADINGS):
        expected = " → ".join(README_HEADINGS)
        found = " → ".join(actual) if actual else "(none)"
        return [f"README.md H2 flow must be exactly: {expected}; found: {found}"]
    return []


def quick_start_body(text: str) -> str | None:
    """Return the Quick start body when the section exists exactly once."""
    matches = [body for name, body in sections(text) if name == "quick start"]
    return matches[0] if len(matches) == 1 else None
