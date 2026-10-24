"""Goal-weighted priority, the delivery frontier, and derived release bundles.

Pure functions over a set of requirement nodes. The per-repository generator and the
organization-level architecture page share them, so one formula gives one score.

priority = (10 x competency-question rows that transitively Depends-on this row
           + 2 x open rows it transitively unblocks) x 0.5 for a non-functional row.

A competency-question (CQ) row is an ordinary spec row whose ID starts with ``EG-CQ-``. A row serves a CQ
when that CQ row reaches it through Depends-on edges. A row is *open* until it is LANDED, VERIFIED or
RETIRED. Nothing hand-edits the score.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, NamedTuple

DONE_STATES = frozenset({"LANDED", "VERIFIED", "RETIRED"})
CQ_WEIGHT = 10
CQ_PREFIX = "EG-CQ-"
#: A row whose spec ID holds one of these words is a gate, page or documentation row, not a feature.
NON_FUNCTIONAL_WORDS = frozenset({"GATES", "PAGES", "DOCS", "HYGIENE", "STANDARD"})
UNBLOCK_WEIGHT = 2
NON_FUNCTIONAL_FACTOR = 0.5

#: Release train: a bundle's steps run in this order. Repositories outside it (connectors) go last.
TRAIN = (
    ("epistemic-graph",),
    ("agent-connector-sdk",),
    ("agent-utilities",),
    ("arbora", "graph-os"),
    ("agent-webui", "agent-terminal-ui", "geniusbot"),
)


class Node(NamedTuple):
    """One requirement row as the scorer sees it."""

    id: str
    repo: str
    state: str
    depends_on: tuple[str, ...] = ()
    functional: bool = True
    rollup: bool = False
    title: str = ""


def is_cq(rid: str) -> bool:
    return rid.startswith(CQ_PREFIX)


def is_functional(spec_id: str) -> bool:
    return not (set(spec_id.split("-")) & NON_FUNCTIONAL_WORDS)


def is_open(node: Node) -> bool:
    return node.state not in DONE_STATES


def _tidy(value: float) -> int | float:
    return int(value) if value == int(value) else round(value, 1)


def _dependents(nodes: dict[str, Node]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = defaultdict(set)
    for node in nodes.values():
        for dep in node.depends_on:
            if dep in nodes:
                reverse[dep].add(node.id)
    return reverse


def transitive(rid: str, reverse: dict[str, set[str]]) -> set[str]:
    """Every row that needs ``rid`` through any chain of Depends-on edges."""
    seen: set[str] = set()
    stack = [rid]
    while stack:
        for nxt in reverse.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    seen.discard(rid)
    return seen


def transitive_open(rid: str, nodes: dict[str, Node], reverse: dict[str, set[str]]) -> set[str]:
    """Open leaf rows that need ``rid`` through any chain of Depends-on edges."""
    return {n for n in transitive(rid, reverse) if is_open(nodes[n]) and not nodes[n].rollup}


def is_blocked(node: Node, nodes: dict[str, Node], *, unknown_blocks: bool) -> bool:
    for dep in node.depends_on:
        target = nodes.get(dep)
        if target is None:
            if unknown_blocks:
                return True
        elif is_open(target):
            return True
    return False


def score(nodes: dict[str, Node]) -> dict[str, dict[str, Any]]:
    """Open row ID -> ``{priority, unblocks, cqs}``. Done rows are absent.

    ``cqs`` lists the CQ rows (open or done) that reach the row through Depends-on.
    """
    reverse = _dependents(nodes)
    out: dict[str, dict[str, Any]] = {}
    for rid, node in nodes.items():
        if not is_open(node):
            continue
        unblocked = len(transitive_open(rid, nodes, reverse))
        cqs = sorted(n for n in transitive(rid, reverse) if is_cq(n))
        raw = CQ_WEIGHT * len(cqs) + UNBLOCK_WEIGHT * unblocked
        value = raw if node.functional else raw * NON_FUNCTIONAL_FACTOR
        out[rid] = {"priority": _tidy(value), "unblocks": unblocked, "cqs": cqs}
    return out


def frontier(nodes: dict[str, Node], *, unknown_blocks: bool = False) -> list[str]:
    """Open leaf rows whose dependencies are all done."""
    return sorted(
        rid
        for rid, node in nodes.items()
        if is_open(node) and not node.rollup and not is_blocked(node, nodes, unknown_blocks=unknown_blocks)
    )


def unserved(nodes: dict[str, Node], scores: dict[str, dict[str, Any]]) -> list[str]:
    """Open functional leaf rows that no competency question reaches (a CQ row itself is linked)."""
    return sorted(
        rid
        for rid, n in nodes.items()
        if is_open(n) and not n.rollup and n.functional and not is_cq(rid) and not scores[rid]["cqs"]
    )


def train_rank(repo: str) -> int:
    for rank, group in enumerate(TRAIN):
        if repo in group:
            return rank
    return len(TRAIN)


def bundles(nodes: dict[str, Node], priorities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Groups of open leaf rows joined by cross-repository Depends-on edges, derived from the rows.

    Each bundle lists ordered steps (a repository and its rows, in release-train order). A row
    names the other bundle rows it unblocks. A bundle's priority is the maximum of its rows'.
    """
    live = {rid: n for rid, n in nodes.items() if is_open(n) and not n.rollup}
    parent = {rid: rid for rid in live}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    linked: set[str] = set()
    for rid, node in live.items():
        for dep in node.depends_on:
            if dep in live and live[dep].repo != node.repo:
                parent[find(rid)] = find(dep)
                linked |= {rid, dep}
    groups: dict[str, list[str]] = defaultdict(list)
    for rid in sorted(linked):
        groups[find(rid)].append(rid)
    reverse = _dependents(live)
    out = []
    for members in groups.values():
        inside = set(members)
        by_repo: dict[str, list[str]] = defaultdict(list)
        for rid in members:
            by_repo[live[rid].repo].append(rid)
        steps = []
        for repo in sorted(by_repo, key=lambda r: (train_rank(r), r)):
            rows = []
            for rid in sorted(by_repo[repo], key=lambda r: (-priorities[r]["priority"], r)):
                unblocks = sorted(transitive_open(rid, live, reverse) & inside)
                rows.append(
                    {
                        "id": rid,
                        "title": live[rid].title,
                        "priority": priorities[rid]["priority"],
                        "unblocks": unblocks,
                    }
                )
            steps.append({"repo": repo, "rows": rows})
        top = max(priorities[r]["priority"] for r in members)
        out.append({"id": "bundle-" + min(members), "priority": top, "rows": len(members), "steps": steps})
    return sorted(out, key=lambda b: (-b["priority"], b["id"]))
