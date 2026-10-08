"""Sentence splitting for masked prose.

A sentence is a maximal run ending in ``.``/``!``/``?``. Tokens from the
abbreviation list (``e.g.`` and friends) do not end a sentence, and runs
with no word tokens are dropped.
"""

from __future__ import annotations

import re

_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'\u2019\-]*")
_BE_FORMS = frozenset({"is", "are", "was", "were", "be", "been", "being"})
_NOUN_LINKS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to",
        "for", "with", "by", "from", "as", "via", "per", "that", "this",
        "these", "those", "it", "its", "which", "who", "whose", "is", "are",
        "was", "were", "be", "been", "being", "not", "no",
    }
)


def words(text: str) -> list[str]:
    """Word tokens in masked prose (code is already masked away)."""
    return _WORD.findall(text)


def _ends_protected(tail: str, protect: frozenset[str]) -> bool:
    lowered = tail.rstrip().casefold()
    for abbr in protect:
        a = abbr.casefold()
        index = len(lowered) - len(a)
        if index < 0 or not lowered.endswith(a):
            continue
        before = lowered[index - 1] if index > 0 else ""
        if before.isalnum():
            continue
        return True
    return False


def sentence_spans(text: str, protect: frozenset[str]) -> list[tuple[int, int]]:
    """(start, exclusive end) character spans, one per sentence."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for match in _SPLIT.finditer(text):
        end = match.start() + 1
        if not _ends_protected(text[pos:end].rstrip(), protect):
            spans.append((pos, end))
            pos = match.end()
    stripped = text.rstrip()
    if len(stripped) > pos:
        spans.append((pos, len(stripped)))
    return spans


def sentences(text: str, protect: frozenset[str]) -> list[tuple[str, int]]:
    """(sentence, offset of its last character) pairs in masked prose."""
    result: list[tuple[str, int]] = []
    for start, end in sentence_spans(text, protect):
        sentence = text[start:end].rstrip()
        if words(sentence):
            result.append((sentence, end - 1))
    return result


def passive_participle(sentence_words: list[str], allowlist: frozenset[str]) -> str | None:
    """The first be-form + participle pair, or None when no passive appears."""
    for verb, follower in zip(sentence_words, sentence_words[1:]):
        if verb.casefold() in _BE_FORMS and follower.casefold() not in allowlist:
            tail = follower.casefold()
            if tail.endswith(("ed", "en")) and len(tail) >= 4:
                return follower
    return None


def noun_run(sentence_words: list[str]) -> int:
    """Longest run of consecutive words that are not function words."""
    best = run = 0
    for word in sentence_words:
        if word.casefold() in _NOUN_LINKS:
            run = 0
        else:
            run += 1
            best = max(best, run)
    return best
