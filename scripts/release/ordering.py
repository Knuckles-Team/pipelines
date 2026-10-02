"""Deterministic dependency order for a validated candidate set (FR-3)."""

from __future__ import annotations

import networkx as nx

from .errors import CandidateSetError
from .models import CandidateSet


def topological_order(candidates: CandidateSet) -> list[str]:
    """Component IDs in a stable dependency order (predecessors before successors).

    Ties are broken alphabetically by component ID so the same candidate set
    always orders the same way, regardless of manifest entry order.
    """
    graph = nx.DiGraph()
    for candidate in candidates.candidates:
        graph.add_node(candidate.component_id)
    for candidate in candidates.candidates:
        for predecessor in candidate.predecessors:
            graph.add_edge(predecessor, candidate.component_id)
    try:
        return list(nx.lexicographical_topological_sort(graph))
    except nx.NetworkXUnfeasible as exc:
        raise CandidateSetError("candidate set contains a dependency cycle") from exc
