"""EG-STE-Lite wordlist: the machine-readable half of the standard.

The TOML file next to this module is package data: it travels with the
installed wheel, and a missing or malformed file is a broken installation
(exit 2), never a silent pass.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

#: Fleet-wide staleness patterns: none shipped in the gate repository. Every
#: staleness pattern comes from the consumer's own configuration table.
DEFAULT_STALENESS: tuple[tuple[str, str], ...] = ()

_WORDLIST = Path(__file__).with_name("ste_words.toml")
_REQUIRED = (
    "general",
    "banned",
    "modal",
    "modal_advisory",
    "fuzzy",
    "fuzzy_advisory",
    "person",
    "idioms",
    "cluster",
    "abbreviations",
    "passive_allowlist",
)


@dataclass(frozen=True)
class Wordlist:
    """A validated wordlist: every entry usable by the scanner."""

    general: frozenset[str]
    banned: Mapping[str, str]
    modal: frozenset[str]
    modal_advisory: frozenset[str]
    fuzzy: frozenset[str]
    fuzzy_advisory: frozenset[str]
    person: frozenset[str]
    idioms: frozenset[str]
    cluster: tuple[tuple[tuple[str, frozenset[str]], tuple[str, frozenset[str]]], ...]
    abbreviations: frozenset[str]
    passive_allowlist: frozenset[str]


def _words(doc: Mapping[str, object], key: str) -> frozenset[str]:
    value = doc[key]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise CannotRun(f"ste wordlist [{key}] must be a list of strings")
    return frozenset(value)


def _banned(doc: Mapping[str, object]) -> dict[str, str]:
    value = doc["banned"]
    if not isinstance(value, Mapping) or not value:
        raise CannotRun("ste wordlist [banned] must be a non-empty mapping")
    if any(not isinstance(term, str) or not isinstance(fix, str) or not fix for term, fix in value.items()):
        raise CannotRun("ste wordlist [banned] entries must map strings to non-empty fixes")
    return dict(value)


def _cluster_member(member: object) -> tuple[str, frozenset[str]]:
    if not isinstance(member, list) or len(member) < 2:
        raise CannotRun("ste wordlist [cluster] members must list base form plus inflections")
    forms = [item for item in member if isinstance(item, str)]
    if len(forms) != len(member) or any(not item for item in forms):
        raise CannotRun("ste wordlist [cluster] members must be lists of strings")
    return forms[0], frozenset(forms)


def _cluster_pair(value: object) -> tuple[tuple[str, frozenset[str]], tuple[str, frozenset[str]]]:
    if not isinstance(value, list) or len(value) != 2:
        raise CannotRun("ste wordlist [cluster] entries must be two form lists")
    return _cluster_member(value[0]), _cluster_member(value[1])


def _cluster(doc: Mapping[str, object]) -> tuple[tuple[tuple[str, frozenset[str]], tuple[str, frozenset[str]]], ...]:
    value = doc["cluster"]
    if not isinstance(value, list):
        raise CannotRun("ste wordlist [cluster] must be a list of pairs")
    return tuple(_cluster_pair(pair) for pair in value)


def load_wordlist() -> Wordlist:
    """The validated wordlist from the package data file."""
    try:
        doc = tomllib.loads(_WORDLIST.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"ste wordlist unreadable at {_WORDLIST}: {exc}") from exc
    missing = [key for key in _REQUIRED if key not in doc]
    if missing:
        raise CannotRun(f"ste wordlist lacks section(s): {', '.join(missing)}")
    return Wordlist(
        general=_words(doc, "general"),
        banned=_banned(doc),
        modal=_words(doc, "modal"),
        modal_advisory=_words(doc, "modal_advisory"),
        fuzzy=_words(doc, "fuzzy"),
        fuzzy_advisory=_words(doc, "fuzzy_advisory"),
        person=_words(doc, "person"),
        idioms=_words(doc, "idioms"),
        cluster=_cluster(doc),
        abbreviations=_words(doc, "abbreviations"),
        passive_allowlist=_words(doc, "passive_allowlist"),
    )
