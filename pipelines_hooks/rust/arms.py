"""Locate ``match`` blocks and read their arm patterns from masked source."""

from __future__ import annotations

import re

from pipelines_hooks.rust.balance import balanced_span_from

OPEN, CLOSE = "([{", ")]}"
_MATCH_KEYWORD = re.compile(r"\bmatch\b")


def skip_space(mask: str, index: int, end: int) -> int:
    while index < end and mask[index].isspace():
        index += 1
    return index


def _pattern_end(mask: str, index: int, end: int) -> int | None:
    """Index of the top-level ``=>`` that terminates an arm pattern."""
    depth = 0
    while index < end - 1:
        char = mask[index]
        if char in CLOSE and depth == 0:
            return None
        depth += (char in OPEN) - (char in CLOSE)
        if depth == 0 and mask.startswith("=>", index):
            return index
        index += 1
    return None


def _expression_arm_end(mask: str, index: int, end: int) -> int:
    """Index past an expression arm body: the next top-level comma or ``}``."""
    depth = 0
    while index < end:
        char = mask[index]
        if char in CLOSE and depth == 0:
            return index
        depth += (char in OPEN) - (char in CLOSE)
        if depth == 0 and char == ",":
            return index + 1
        index += 1
    return end


def _arm_body_end(mask: str, index: int, end: int) -> int | None:
    """Index past one arm's body: a block, or an expression up to a comma."""
    index = skip_space(mask, index, end)
    if index >= end:
        return None
    if mask[index] != "{":
        return _expression_arm_end(mask, index, end)
    after = skip_space(mask, balanced_span_from(mask, index, opener="{", closer="}") + 1, end)
    return after + 1 if after < end and mask[after] == "," else after


def match_blocks(mask: str, start: int, end: int) -> list[tuple[int, int]]:
    """Brace span of every ``match`` expression inside ``[start, end)``.

    Rust forbids an unparenthesised struct literal in a scrutinee, so the first
    ``{`` outside parentheses and brackets always opens the arm block.
    """
    blocks: list[tuple[int, int]] = []
    for keyword in _MATCH_KEYWORD.finditer(mask, start, end):
        index, depth = keyword.end(), 0
        while index < end and not (mask[index] == "{" and depth == 0):
            depth += (mask[index] in "([") - (mask[index] in ")]")
            index += 1
        if index < end:
            blocks.append((index, balanced_span_from(mask, index, opener="{", closer="}")))
    return blocks


def _skip_attributes(mask: str, index: int, closing: int) -> int | None:
    index = skip_space(mask, index, closing)
    while index < closing and mask[index] == "#":
        bracket = mask.find("[", index, closing)
        if bracket < 0:
            return None
        after = balanced_span_from(mask, bracket, opener="[", closer="]") + 1
        index = skip_space(mask, after, closing)
    return index


def arm_patterns(mask: str, opening: int, closing: int) -> list[str]:
    """Every arm pattern text in one match block, in source order."""
    patterns: list[str] = []
    index: int | None = opening + 1
    while index is not None:
        index = _skip_attributes(mask, index, closing)
        arrow = None if index is None or index >= closing else _pattern_end(mask, index, closing)
        if index is None or arrow is None:
            break
        patterns.append(mask[index:arrow])
        following = _arm_body_end(mask, arrow + 2, closing)
        index = following if following is not None and following > arrow else None
    return patterns
