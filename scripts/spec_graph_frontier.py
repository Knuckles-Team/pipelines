"""Dependency edges and the per-repo UNBLOCKED frontier (section 1 of
``plans/refactor/reconciliation-20261006/SPEC-SIZING-AND-DEPENDENCIES.md``).
"""

from __future__ import annotations

if __package__:
    from .spec_graph_core import LANDED_STATES, Requirement
    from .spec_graph_score import size_score
else:
    from spec_graph_core import LANDED_STATES, Requirement
    from spec_graph_score import size_score


def is_open(req: Requirement) -> bool:
    return req.delivery_state not in LANDED_STATES


def is_unblocked(req: Requirement, delivery_states: dict[str, str]) -> bool:
    return all(
        delivery_states.get(dep, "UNKNOWN") in LANDED_STATES for dep in req.depends_on
    )


def build_reverse_adjacency(reqs: dict[str, Requirement]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {}
    for rid, req in reqs.items():
        for dep in req.depends_on:
            reverse.setdefault(dep, set()).add(rid)
    return reverse


def transitive_dependents(rid: str, reverse_adj: dict[str, set[str]]) -> int:
    seen: set[str] = set()
    stack = [rid]
    while stack:
        current = stack.pop()
        for nxt in reverse_adj.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return len(seen)


def dependency_edges(reqs: dict[str, Requirement]) -> list[tuple[str, str]]:
    return sorted((rid, dep) for rid, req in reqs.items() for dep in req.depends_on)


def frontier(reqs: dict[str, Requirement]) -> dict[str, list[dict[str, object]]]:
    """The UNBLOCKED frontier per repo, highest transitive-dependents first,
    then smallest size score, then ID for a stable tie-break."""
    delivery_states = {rid: req.delivery_state for rid, req in reqs.items()}
    reverse_adj = build_reverse_adjacency(reqs)
    per_repo: dict[str, list[dict[str, object]]] = {}
    for rid, req in reqs.items():
        if not (is_open(req) and is_unblocked(req, delivery_states)):
            continue
        row = {
            "id": rid,
            "dependents": transitive_dependents(rid, reverse_adj),
            "score": size_score(req, delivery_states),
        }
        per_repo.setdefault(req.repo, []).append(row)
    for rows in per_repo.values():
        rows.sort(key=lambda row: (-row["dependents"], row["score"], row["id"]))
    return per_repo
