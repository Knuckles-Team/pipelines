"""Spec relationship model: spec-level edges and dependency layers (PIPE-PAGES-R013.1-3)."""

import re

DEPENDS = "depends on"
EXTENDS = "extends"
EXTENDS_LINE = re.compile(r"^Extends:\s*(\S+)", re.MULTILINE)


def spec_edges(requirements):
    """Lift requirement `depends_on` edges to spec pairs; one edge per pair."""
    spec_of = {req.id: req.spec for req in requirements}
    pairs = {
        (req.spec, DEPENDS, spec_of[dep])
        for req in requirements
        for dep in req.depends_on
        if dep in spec_of
    }
    return sorted(edge for edge in pairs if edge[0] != edge[2])


def extends_edges(spec_texts):
    """Read the `Extends: <ID>` line of each spec.md text; no other source."""
    edges = set()
    for spec, text in spec_texts.items():
        found = EXTENDS_LINE.search(text)
        if found and found.group(1) != spec:
            edges.add((spec, EXTENDS, found.group(1).strip("`.,")))
    return sorted(edges)


def reach(adjacent, start):
    seen, todo = set(), [start]
    while todo:
        for nxt in adjacent.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def components(nodes, edges):
    """Map each node to its strongly connected component representative (smallest member)."""
    adjacent = {}
    for src, _, tgt in edges:
        adjacent.setdefault(src, set()).add(tgt)
    reaches = {node: reach(adjacent, node) | {node} for node in nodes}
    return {node: min(m for m in reaches[node] if node in reaches[m]) for node in nodes}


def layer_specs(nodes, edges):
    """Longest dependency depth per spec after collapsing cycles; roots are layer 0."""
    nodes = sorted(set(nodes))
    comp = components(nodes, edges)
    deps = {}
    for src, _, tgt in edges:
        if src in comp and tgt in comp and comp[src] != comp[tgt]:
            deps.setdefault(comp[src], set()).add(comp[tgt])
    depth = {}

    def of(rep):
        if rep not in depth:
            depth[rep] = 1 + max((of(dep) for dep in deps.get(rep, ())), default=-1)
        return depth[rep]

    return {node: of(comp[node]) for node in nodes}
