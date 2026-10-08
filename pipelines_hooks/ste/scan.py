"""EG-STE-Lite scanner: rules 1, 2, 4, 5, 6, 7 over masked prose.

Rule 3 (tense) is convention, not a scanner: tense is enforced by the
wordlist rules below plus review. Passive voice and noun chains are
advisory heuristics (noisy by design) and never fail a gate.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from re import Match

from pipelines_hooks.ste.prose import Para, mask_lines, paragraphs
from pipelines_hooks.ste.sentences import noun_run, passive_participle, sentences, words
from pipelines_hooks.ste.words import Wordlist

_SENTENCE_CAP = 20
_NOUN_CHAIN_CAP = 5


@dataclass(frozen=True)
class Finding:
    """One scanner hit, reportable and diff-scopable."""

    code: str
    path: str
    line: int
    message: str
    advisory: bool = False


def hits(text: str, term: str) -> Iterator[Match[str]]:
    """Whole-word, case-insensitive matches of ``term`` in masked text."""
    return re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE)


@dataclass(frozen=True)
class _Tier:
    code: str
    terms: frozenset[str]
    render: Callable[[str], str]
    advisory: bool = False


def _term_findings(
    line: str,
    tier: _Tier,
    *,
    path: str,
    number: int,
) -> list[Finding]:
    out: list[Finding] = []
    for term in tier.terms:
        for _ in hits(line, term):
            out.append(Finding(tier.code, path, number, tier.render(term), advisory=tier.advisory))
    return out


def _tiers(wordlist: Wordlist) -> dict[str, _Tier]:
    return {
        "modal": _Tier("M", wordlist.modal, lambda t: f"modal hedge '{t}'; state the requirement with must, should, or may"),
        "modal_adv": _Tier("M", wordlist.modal_advisory, lambda t: "modal 'can' states capability; keep it to capability claims only", True),
        "fuzzy": _Tier("Q", wordlist.fuzzy, lambda t: f"fuzzy quantity '{t}'; state a measured value or mark it measured: ~N"),
        "fuzzy_adv": _Tier("Q", wordlist.fuzzy_advisory, lambda t: "fuzzy quantity 'some'; state a measured value or mark it measured: ~N", True),
        "person": _Tier("P", wordlist.person, lambda t: f"first/second person '{t}'; name the actor instead"),
        "idiom": _Tier("I", wordlist.idioms, lambda t: f"idiom '{t}'; say it in plain language"),
    }


_DOC_TIERS = ("modal", "modal_adv", "fuzzy", "fuzzy_adv", "person", "idiom")
_CLI_TIERS = ("modal", "fuzzy", "person")


def line_findings(
    line: str,
    *,
    path: str,
    number: int,
    wordlist: Wordlist,
    tiers: tuple[str, ...] = _DOC_TIERS,
) -> list[Finding]:
    """Banned plus the named tiers, evaluated per masked line; CLI strings use ``_CLI_TIERS``."""
    table = _tiers(wordlist)
    out: list[Finding] = [
        Finding("B", path, number, f"{term} -> {fix}")
        for term, fix in wordlist.banned.items()
        for _ in hits(line, term)
    ]
    for name in tiers:
        out += _term_findings(line, table[name], path=path, number=number)
    return out


def _sentence_findings(para: Para, path: str, wordlist: Wordlist) -> list[Finding]:
    out: list[Finding] = []
    for sentence, offset in sentences(para.text, wordlist.abbreviations):
        line = para.line_at(offset)
        count = len(words(sentence))
        if count > _SENTENCE_CAP:
            out.append(Finding("S", path, line, f"{count}-word sentence; the cap is {_SENTENCE_CAP}"))
        tokens = words(sentence)
        participle = passive_participle(tokens, wordlist.passive_allowlist)
        if participle:
            out.append(Finding("PV", path, line, f"passive voice '{participle}'; name the actor", advisory=True))
        if noun_run(tokens) >= _NOUN_CHAIN_CAP:
            out.append(Finding("NC", path, line, "five-or-more stacked content words; split the subject", advisory=True))
    return out


def _first_line(masked: list[str], forms: frozenset[str]) -> int | None:
    for number, line in enumerate(masked, 1):
        for form in forms:
            if next(hits(line, form), None) is not None:
                return number
    return None


def _cluster_findings(masked: list[str], path: str, wordlist: Wordlist) -> list[Finding]:
    out: list[Finding] = []
    for first, second in wordlist.cluster:
        seen: list[tuple[int, str]] = []
        for base, forms in (first, second):
            line = _first_line(masked, forms)
            if line is not None:
                seen.append((line, base))
        if len(seen) == 2:
            out.append(
                Finding("C", path, max(line for line, _ in seen),
                        f"cluster terms {seen[0][1]} and {seen[1][1]} both present; pick one term")
            )
    return out


def check_document(text: str, wordlist: Wordlist, *, path: str) -> list[Finding]:
    """Every rule occurrence for one document's text, in order."""
    masked = mask_lines(text)
    findings: list[Finding] = []
    for number, line in enumerate(masked, 1):
        if line:
            findings.extend(line_findings(line, path=path, number=number, wordlist=wordlist))
    for para in paragraphs(masked):
        findings.extend(_sentence_findings(para, path, wordlist))
    findings.extend(_cluster_findings(masked, path, wordlist))
    return findings
