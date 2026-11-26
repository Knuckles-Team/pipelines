"""Canopy code view (PIPE-PAGES-R048): communities and row links from a Medulla code-graph snapshot.

The build never parses source. One snapshot per repository is read as JSON of the shape
``{"repo": str, "items": [{"id", "digest", "path"}], "edges": [[from_id, to_id], ...]}``.
Communities come from Leiden clustering with a fixed seed. A rebuild keeps the previous assignment
(``state``: ``{"digests": {id: digest}, "assignment": {id: community}}``) and re-clusters only the items
whose digest changed and their direct neighbours; ``canopy.code_view.full_recluster_share`` is the changed
share above which everything is re-clustered. A repository with no snapshot has no code view.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import networkx as nx

SEED = 20261126
FULL_RECLUSTER_SHARE = 0.2  # canopy.code_view.full_recluster_share


def read_snapshot(directory: Path | None, repo: str) -> dict | None:
    """The repository's code-graph snapshot, or None when none exists (no code view, no error)."""
    if directory is None:
        return None
    path = directory / f"{repo}.json"
    if not path.is_file():
        return None
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(snapshot.get("items"), list) or not isinstance(snapshot.get("edges"), list):
        raise ValueError(f"code-graph snapshot {path.name} lacks items or edges")
    return snapshot


def _graph(snapshot: dict, only: set[str] | None = None) -> nx.Graph:
    graph = nx.Graph()
    ids = {item["id"] for item in snapshot["items"]}
    graph.add_nodes_from(sorted(ids if only is None else only))
    for a, b in snapshot["edges"]:
        if a in graph and b in graph and a != b:
            graph.add_edge(a, b)
    return graph


def _gain(links: float, strength: float, total: float, two_m: float) -> float:
    """Modularity gain of putting a node of ``strength`` into a community of ``total`` with ``links`` into it."""
    return links - strength * total / two_m


def _move(adj: dict, strength: dict, part: dict, rng: random.Random) -> bool:
    """Local moving: each node joins the neighbouring community with the best positive gain, until none moves."""
    two_m = sum(strength.values()) or 1.0
    total: dict = {}
    for node, community in part.items():
        total[community] = total.get(community, 0.0) + strength[node]
    moved_any, moved = False, True
    while moved:
        moved = False
        order = sorted(adj)
        rng.shuffle(order)
        for node in order:
            links: dict = {}
            for other, weight in adj[node].items():
                if other != node:
                    links[part[other]] = links.get(part[other], 0.0) + weight
            here = part[node]
            total[here] -= strength[node]
            best, best_gain = here, _gain(links.get(here, 0.0), strength[node], total[here], two_m)
            for community in sorted(links):
                gain = _gain(links[community], strength[node], total[community], two_m)
                if gain > best_gain + 1e-12:
                    best, best_gain = community, gain
            total[best] += strength[node]
            if best != here:
                part[node], moved, moved_any = best, True, True
    return moved_any


def _refine(adj: dict, strength: dict, part: dict, rng: random.Random) -> dict:
    """Leiden refinement: split each community into well-connected sub-communities, merging greedily."""
    two_m = sum(strength.values()) or 1.0
    refined = {node: node for node in adj}
    size = {node: strength[node] for node in adj}
    community_total: dict = {}
    for node, community in part.items():
        community_total[community] = community_total.get(community, 0.0) + strength[node]
    order = sorted(adj)
    rng.shuffle(order)
    for node in order:
        if sum(1 for n in refined.values() if n == refined[node]) != 1:
            continue  # only a still-singleton node moves
        community = part[node]
        inside = sum(w for o, w in adj[node].items() if o != node and part[o] == community)
        if inside < strength[node] * (community_total[community] - strength[node]) / two_m:
            continue  # not well connected to its community
        links: dict = {}
        for other, weight in adj[node].items():
            if other != node and part[other] == community:
                links[refined[other]] = links.get(refined[other], 0.0) + weight
        best, best_gain = refined[node], 0.0
        for target in sorted(links):
            gain = _gain(links[target], strength[node], size[target], two_m)
            if gain > best_gain + 1e-12:
                best, best_gain = target, gain
        if best != refined[node]:
            size[refined[node]] -= strength[node]
            size[best] += strength[node]
            refined[node] = best
    return refined


def _aggregate(adj: dict, refined: dict) -> tuple[dict, dict]:
    merged: dict = {}
    for node, neighbours in adj.items():
        for other, weight in neighbours.items():
            a, b = refined[node], refined[other]
            merged.setdefault(a, {})
            merged[a][b] = merged[a].get(b, 0.0) + weight
    strength = {n: sum(w for w in row.values()) for n, row in merged.items()}
    return merged, strength


def _leiden(graph: nx.Graph) -> list[list[str]]:
    """Leiden communities (local moving, refinement, aggregation) with a fixed seed: equal input, equal output."""
    rng = random.Random(SEED)
    adj = {n: {m: 1.0 for m in graph[n]} for n in sorted(graph)}
    strength = {n: float(len(adj[n])) for n in adj}
    members = {n: [n] for n in adj}
    part = {n: n for n in adj}
    while True:
        _move(adj, strength, part, rng)
        if len(set(part.values())) == len(adj):
            break
        refined = _refine(adj, strength, part, rng)
        if len(set(refined.values())) == len(adj):
            refined = dict(part)  # nothing refined further: aggregate by the communities themselves
        members = {r: [m for n, rr in refined.items() if rr == r for m in members[n]] for r in set(refined.values())}
        adj, strength = _aggregate(adj, refined)
        part = {r: community for n, community in part.items() for r in [refined[n]]}
    groups: dict = {}
    for node, community in part.items():
        groups.setdefault(community, []).extend(members[node])
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


def cluster(snapshot: dict, state: dict | None, share: float = FULL_RECLUSTER_SHARE) -> tuple[dict, dict]:
    """The new ``{item: community}`` assignment and the report of what was re-clustered."""
    digests = {item["id"]: item["digest"] for item in snapshot["items"]}
    previous = (state or {}).get("assignment", {})
    old = (state or {}).get("digests", {})
    changed = {i for i, d in digests.items() if old.get(i) != d or i not in previous}
    graph = _graph(snapshot)
    touched = set(changed)
    for item in changed:
        touched.update(graph.neighbors(item))
    if not state or not digests or len(changed) / len(digests) > share:
        parts = _leiden(graph) if digests else []
        assignment = {i: n for n, part in enumerate(parts) for i in part}
        return assignment, {"mode": "full", "reclustered": len(digests), "changed": len(changed)}
    assignment = {i: c for i, c in previous.items() if i in digests and i not in touched}
    base = max(assignment.values(), default=-1) + 1
    for n, part in enumerate(_leiden(_graph(snapshot, touched))):
        for item in part:
            assignment[item] = base + n
    return assignment, {"mode": "incremental", "reclustered": len(touched), "changed": len(changed)}


def link_rows(rows: list[dict], items: list[dict]) -> dict:
    """Row to items and item to rows links: an item is reached by a row's test bindings and named files."""
    by_path: dict[str, list[str]] = {}
    for item in items:
        by_path.setdefault(item.get("path", ""), []).append(item["id"])
    row_items: dict[str, list[str]] = {}
    item_rows: dict[str, list[str]] = {}
    for row in rows:
        paths = {t.partition(":")[0] for t in row.get("verified_by") or [] if isinstance(t, str)}
        paths.update(row.get("paths") or [])
        for path in sorted(paths):
            for item_id in by_path.get(path, ()):
                row_items.setdefault(row["id"], []).append(item_id)
                item_rows.setdefault(item_id, []).append(row["id"])
    return {"row_items": row_items, "item_rows": item_rows}


def build_view(snapshot: dict | None, rows: list[dict], state: dict | None, share: float = FULL_RECLUSTER_SHARE):
    """The code view of one repository and its new state, or ``(None, None)`` without a snapshot."""
    if snapshot is None:
        return None, None
    assignment, report = cluster(snapshot, state, share)
    communities: dict[int, list[str]] = {}
    for item, community in sorted(assignment.items()):
        communities.setdefault(community, []).append(item)
    view = {
        "communities": {str(c): members for c, members in sorted(communities.items())},
        "links": link_rows(rows, snapshot["items"]),
        "recluster": report,
    }
    return view, {"digests": {i["id"]: i["digest"] for i in snapshot["items"]}, "assignment": assignment}


def attach(snaps: list, directory: Path | None, share: float = FULL_RECLUSTER_SHARE) -> dict[str, dict]:
    """Set ``code_view`` on each snapshot that has a code graph and keep the cluster state for the next rebuild."""
    summaries: dict[str, dict] = {}
    for snap in snaps:
        snapshot = read_snapshot(directory, snap.repo)
        state_path = None if directory is None else directory / ".state" / f"{snap.repo}.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path and state_path.is_file() else None
        view, new_state = build_view(snapshot, snap.rows, state, share)
        if view is None or state_path is None:
            continue
        snap.code_view = view
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, sort_keys=True), encoding="utf-8")
        summaries[snap.repo] = {"items": len(new_state["assignment"]), "communities": len(view["communities"])}
    return summaries
