"""Prose extraction: everything that is not prose is masked before scanning.

Line structure (and therefore line numbers) is preserved: masked regions
collapse to blanks. What gets masked is fenced code blocks, inline images
(badges carry no prose), inline code spans, all-caps tokens (env vars,
acronyms), ``CONCEPT:`` identifiers, ``Method::`` names, URLs (scheme-qualified and
markdown-link targets, while the link text stays prose), generated
blocks (``<!-- generated:begin -->`` to ``<!-- generated:end -->``), and
markdown line-level structure such as heading markers, list markers, and
table rows. A structural line is its own paragraph unit: a table row or
bullet that carries no end-of-sentence punctuation must not merge with its
neighbours into one run-on sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE = re.compile(r"(```|~~~)")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_CODE_SPAN = re.compile(r"`[^`]*`")
_URL = re.compile(r"\b(?:https?|ftp)://\S+")
_MD_LINK_URL = re.compile(r"(?<=\])\([^)]*\)")
_CONCEPT = re.compile(r"\bCONCEPT:[A-Za-z0-9._/\-]+")
_METHOD = re.compile(r"\b[A-Z][A-Za-z0-9_]*::[A-Za-z0-9_]+")
_ALLCAPS = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_HEADING = re.compile(r"^\s*(?:#{1,6}\s+|\d+[.)]\s+|[-+>]\s+|\|)+")
_MARKUP = re.compile(r"[*_]")
_STRUCTURAL = "\x00"


@dataclass(frozen=True)
class Para:
    """A contiguous block of masked prose lines, with their line numbers."""

    lines: tuple[tuple[int, str], ...]

    @property
    def text(self) -> str:
        return " ".join(text for _, text in self.lines)

    @property
    def line(self) -> int:
        return self.lines[0][0]

    def line_at(self, offset: int) -> int:
        pos = 0
        for number, text in self.lines:
            if offset <= pos + len(text):
                return number
            pos += len(text) + 1
        return self.lines[-1][0]


def _mask_inline(raw: str) -> str:
    masked = _IMAGE.sub(" ", raw)
    masked = _CODE_SPAN.sub(" ", masked)
    masked = _URL.sub(" ", masked)
    masked = _MD_LINK_URL.sub(" ", masked)
    masked = _CONCEPT.sub(" ", masked)
    masked = _METHOD.sub(" ", masked)
    masked = _ALLCAPS.sub(" ", masked)
    masked = _HEADING.sub(_STRUCTURAL, masked, count=1)
    masked = _MARKUP.sub(" ", masked)
    return masked.strip()


def mask_lines(text: str) -> list[str]:
    """Masked lines, one per source line (blank means fully masked)."""
    masked: list[str] = []
    fence = False
    generated = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if _FENCE.match(stripped):
            fence = not fence
            masked.append("")
            continue
        if fence:
            masked.append("")
            continue
        if stripped.startswith("<!-- generated:begin"):
            generated = True
            masked.append("")
            continue
        if generated:
            if stripped.startswith("<!-- generated:end"):
                generated = False
            masked.append("")
            continue
        masked.append(_mask_inline(raw))
    return masked


def paragraphs(masked: list[str]) -> list[Para]:
    """Masked lines grouped into paragraphs; a structural line is alone.

    A structural line (heading, bullet, table row, numbered item) carries
    no paragraph boundary punctuation and must not merge with its
    neighbours, so it forms a single-line block.
    """
    blocks: list[Para] = []
    current: list[tuple[int, str]] = []
    for number, text in enumerate(masked, 1):
        structural = text.startswith(_STRUCTURAL)
        if text and not structural:
            current.append((number, text))
            continue
        if current:
            blocks.append(Para(lines=tuple(current)))
            current = []
        if text:
            blocks.append(Para(lines=((number, text),)))
    if current:
        blocks.append(Para(lines=tuple(current)))
    return blocks
