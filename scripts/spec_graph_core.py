"""Shared data model and text primitives for the deterministic spec graph.

See ``scripts/spec_graph.py`` for the CLI and
``plans/refactor/reconciliation-20261006/SPEC-SIZING-AND-DEPENDENCIES.md`` for
the rules this implements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Every requirement-ID prefix observed across the five repos is a run of
#: hyphen-separated upper-case/digit segments ending in an optional ``R`` plus
#: digits, with an optional ``.<n>`` split suffix: ``EG-DECISION-ENGINE-R048``,
#: ``AU-SEMANTIC-R005``, ``SDK-GOVERNED-WRITEBACK-R002``, ``IDUI-01``,
#: ``EG-DECISION-ENGINE-R030.1``.
REQ_ID = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R?\d+(?:\.\d+)*\b")

#: Inline-code spans that look like a code root (crate, package or module
#: path): at least one ``/`` and no URL scheme.
CODE_ROOT = re.compile(r"`([\w.-]+(?:/[\w.-]+)+)`")

KNOWN_REPOS = (
    "epistemic-graph",
    "agent-connector-sdk",
    "agent-utilities",
    "graph-os",
    "agent-webui",
    "pipelines",
)
LANDED_STATES = frozenset({"LANDED", "CLOSED"})
SPLIT_THRESHOLD = 6


@dataclass
class Requirement:
    """One requirement, as reconstructed from its owning repo's spec files."""

    id: str
    repo: str
    spec: str
    title: str
    delivery_state: str
    requirement_text: str = ""
    verification_text: str = ""
    code_roots: set[str] = field(default_factory=set)
    other_repos: set[str] = field(default_factory=set)
    depends_on: set[str] = field(default_factory=set)
    unchecked_tasks: int = 0
    test_mentions: int = 0


def find_ids(text: str) -> set[str]:
    return set(REQ_ID.findall(text))


def apply_signals(req: Requirement, text: str) -> None:
    """Fold the code roots and other-repository mentions in ``text`` into ``req``."""
    req.code_roots |= set(CODE_ROOT.findall(text))
    for name in KNOWN_REPOS:
        if name != req.repo and re.search(rf"\b{re.escape(name)}\b", text):
            req.other_repos.add(name)


def add_edge(
    req: Requirement, other_ids: set[str], known: dict[str, Requirement]
) -> None:
    """Only a textually-named ID that is a real, declared requirement (in
    ``known``) becomes a dependency edge -- this is what keeps a spec file's
    own local test/case numbering scheme (for example ``EG-T-04``, which
    matches the requirement-ID shape but is never declared in any
    ``status.json``) from being mistaken for a requirement dependency."""
    req.depends_on |= (other_ids & known.keys()) - {req.id}
