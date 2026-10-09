"""Per-finding-kind checks for ``spec-decomposition``.

Each ``find_*`` function here looks for exactly one failure kind described in
``decomposition.py``'s module docstring (duplicates, untracked children,
status-without-requirement, parent-done-child-open, orphan children).
``decomposition.check_spec`` builds a :class:`SpecIndex` once per spec
directory and runs every ``find_*`` function against it.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass



def parent_of(id_: str) -> str | None:
    """The immediate parent of a dotted child ID, or ``None`` for a root ID."""
    m = re.match(r"(.+)\.\d+$", id_)
    return m.group(1) if m else None


@dataclass(frozen=True)
class SpecIndex:
    """Everything a single finding check needs about one ``specs/<dir>/``."""

    label: str
    req_counts: Counter[str]
    status_counts: Counter[str]
    state_by_id: dict[str, str]
    referenced: set[str]


def find_duplicates(idx: SpecIndex) -> list[str]:
    """(a) an ID appears twice, in requirements.md rows or in status.json rows."""
    findings: list[str] = []
    for id_, count in sorted(idx.req_counts.items()):
        if count > 1:
            findings.append(
                f"{idx.label}: duplicate ID {id_} appears {count}x in requirements.md"
            )
    for id_, count in sorted(idx.status_counts.items()):
        if count > 1:
            findings.append(
                f"{idx.label}: duplicate ID {id_} appears {count}x in status.json"
            )
    return findings


def find_untracked_children(idx: SpecIndex) -> list[str]:
    """(b) a referenced child has no status.json row."""
    return [
        f"{idx.label}: child {id_} is referenced but has no status.json row"
        for id_ in sorted(idx.referenced)
        if id_ not in idx.status_counts
    ]


def find_status_without_requirement(idx: SpecIndex) -> list[str]:
    """(c) a status.json row has no requirements.md row."""
    return [
        f"{idx.label}: status.json row {id_} has no requirements.md row"
        for id_ in sorted(idx.status_counts)
        if id_ not in idx.req_counts
    ]


def _children_of(status_counts: Counter[str]) -> dict[str, list[str]]:
    """Map each parent ID to the status.json-tracked children it has."""
    children_of: dict[str, list[str]] = {}
    for id_ in status_counts:
        parent = parent_of(id_)
        if parent:
            children_of.setdefault(parent, []).append(id_)
    return children_of


#: Delivery progress rank shared by schema v1 and v2; a rollup parent may never be
#: ahead of a live child (v2 rollup = minimum of children). Retired children are ignored.
STATE_RANK = {"LANDED": 1, "ACCEPTED": 2, "VERIFIED": 2}
IGNORED_CHILD = {"CLOSED", "RETIRED"}


def find_parent_done_child_open(idx: SpecIndex) -> list[str]:
    """(d) a parent is further along than one of its live children."""
    findings: list[str] = []
    for parent, children in sorted(_children_of(idx.status_counts).items()):
        parent_rank = STATE_RANK.get(idx.state_by_id.get(parent) or "", 0)
        if parent_rank == 0:
            continue
        for child in sorted(children):
            child_state = idx.state_by_id.get(child) or ""
            if (
                child_state not in IGNORED_CHILD
                and STATE_RANK.get(child_state, 0) < parent_rank
            ):
                findings.append(
                    f"{idx.label}: parent {parent} is {idx.state_by_id.get(parent)} but "
                    f"child {child} is {child_state or 'UNKNOWN'}"
                )
    return findings


def find_orphan_children(idx: SpecIndex) -> list[str]:
    """(e) a child exists (tracked or merely referenced) but its parent has no row at all."""
    findings: list[str] = []
    for id_ in sorted({*idx.status_counts, *idx.referenced}):
        parent = parent_of(id_)
        if parent and parent not in idx.status_counts and parent not in idx.req_counts:
            findings.append(
                f"{idx.label}: child {id_} exists but parent {parent} has no row at all"
            )
    return findings
