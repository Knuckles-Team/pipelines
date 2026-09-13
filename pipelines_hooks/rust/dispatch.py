"""Terms of acceptance for Rust exhaustive dispatch under the cyclomatic cap.

Cyclomatic complexity charges every ``match`` arm as a decision point. For a
flat, exhaustive ``match`` that is arithmetically correct and semantically
empty, and decomposing it trades away rustc's exhaustiveness guarantee: while
the match names every variant, adding a variant is a COMPILE ERROR at every
dispatch site. This module states a RULE about that class of code and
recomputes membership from the source under measurement on every run. It holds
no list of files or functions and no count.

A Rust function may exceed the cyclomatic cap -- never the cognitive cap --
only if ALL four hold:

1. its cognitive complexity is within the cognitive cap;
2. its body contains at least one ``match``;
3. no arm of any ``match`` in the body is irrefutable (``_``, a bare binding,
   ``x @ _``, with or without a guard, or an alternation containing one);
4. its residual cyclomatic complexity (measured minus arms) is within the
   same cyclomatic cap every other function obeys.

Anything the rule cannot prove -- non-Rust source, unlexable text, a start line
with no body, an arm count above the measured value -- is not exempt.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from pipelines_hooks.rust.arms import CLOSE, OPEN, arm_patterns, match_blocks
from pipelines_hooks.rust.balance import balanced_span_from
from pipelines_hooks.rust.mask import RustLexError, code_mask

#: An arm pattern that binds instead of discriminating: ``_``, a bare
#: lowercase binding, or ``ident @ _``. Rust naming makes this unambiguous: a
#: unit variant or constant is UpperCamel/SCREAMING_CASE or a ``::`` path.
IRREFUTABLE = re.compile(r"^(?:ref\s+)?(?:mut\s+)?(?:_|[a-z][A-Za-z0-9_]*)(?:\s*@\s*_)?$")


class DispatchShape(NamedTuple):
    """Every arm of every ``match`` in a function body, nested ones included."""

    arms: int
    catch_alls: int


def _without_guard(pattern: str) -> str:
    """The pattern with any ``if`` guard removed (a guarded binding still counts)."""
    depth = 0
    for token in re.finditer(r"[()\[\]{}]|\bif\b", pattern):
        text = token.group(0)
        if text == "if" and depth == 0:
            return pattern[: token.start()]
        depth += (text in OPEN) - (text in CLOSE)
    return pattern


def is_catch_all(pattern: str) -> bool:
    """Whether any top-level alternative of an arm pattern is irrefutable."""
    body = _without_guard(pattern)
    depth, alternatives, start = 0, [], 0
    for index, char in enumerate(body):
        depth += (char in OPEN) - (char in CLOSE)
        if char == "|" and depth == 0:
            alternatives.append(body[start:index])
            start = index + 1
    alternatives.append(body[start:])
    return any(IRREFUTABLE.match(item.strip()) for item in alternatives if item.strip())


def _body_open(source: str, mask: str, line: int) -> int | None:
    offsets = [0]
    for text in source.split("\n"):
        offsets.append(offsets[-1] + len(text) + 1)
    if line < 1 or line >= len(offsets):
        return None
    opening = mask.find("{", offsets[line - 1])
    return None if opening < 0 else opening


def _function_arm_patterns(source: str, line: int) -> list[str] | None:
    mask = code_mask(source)
    opening = _body_open(source, mask, line)
    if opening is None:
        return None
    closing = balanced_span_from(mask, opening, opener="{", closer="}")
    return [
        pattern
        for block_open, block_close in match_blocks(mask, opening, closing)
        for pattern in arm_patterns(mask, block_open, block_close)
    ]


def dispatch_shape(source: str, line: int) -> DispatchShape | None:
    """The match-arm shape of the function starting at ``line``, or ``None``."""
    try:
        patterns = _function_arm_patterns(source, line)
    except (RustLexError, IndexError, RecursionError):
        return None
    if patterns is None:
        return None
    return DispatchShape(len(patterns), sum(is_catch_all(p) for p in patterns))


def exhaustive_dispatch_exempt(
    source: str | None, *, line: int, metrics: tuple[int, int], caps: tuple[int, int]
) -> bool:
    """Whether the four conditions hold. ``metrics``/``caps`` are (cyclomatic, cognitive).

    ``source`` is the Rust text under measurement (the STAGED blob in a
    pre-commit run), or ``None`` for a non-Rust file, which is never exempt.
    """
    cyclomatic, cognitive = metrics
    max_cyclomatic, max_cognitive = caps
    if source is None or cognitive > max_cognitive or cyclomatic <= max_cyclomatic:
        return False
    shape = dispatch_shape(source, line)
    if shape is None or shape.arms == 0 or shape.catch_alls:
        return False
    return 1 <= cyclomatic - shape.arms <= max_cyclomatic
