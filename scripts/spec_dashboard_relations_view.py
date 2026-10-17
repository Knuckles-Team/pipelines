"""HTML/CSS relationship view, legend and text-alternative table (PIPE-PAGES-R013.4-7)."""

import html
from collections import Counter

if __package__:
    from .spec_dashboard_relations import layer_specs
else:
    from spec_dashboard_relations import layer_specs

CAP = 40
GROUPS = ("verified", "landed", "specified", "invalid")
GROUP_OF = {"verified": "verified", "landed": "landed", "specified": "specified"}
STYLE = (
    "<style>.rel-view{display:flex;gap:16px;align-items:flex-start;overflow-x:auto}"
    ".rel-col{display:flex;flex-direction:column;gap:8px;min-width:150px}"
    ".rel-box{border:1px solid currentColor;padding:6px;font-size:12px}"
    ".rel-link{display:block;margin-left:8px;border-left:2px solid currentColor;padding-left:4px}"
    ".rel-verified{color:#1a7f37}.rel-landed{color:#0969da}.rel-invalid{color:#cf222e}"
    ".rel-specified{color:#57606a}</style>"
)


def state_counts(states):
    """Group record states into the four displayed counts."""
    counts = Counter(GROUP_OF.get(state, "invalid") for state in states)
    return {group: counts[group] for group in GROUPS}


def box(spec, counts, edges):
    links = "".join(
        f'<span class="rel-link"><b>{html.escape(label)}</b> {html.escape(tgt)}</span>'
        for src, label, tgt in edges
        if src == spec
    )
    stats = " ".join(f'<span class="rel-{group}">{group} {counts.get(group, 0)}</span>' for group in GROUPS)
    return f'<div class="rel-box"><b><a href="#spec-{html.escape(spec)}">{html.escape(spec)}</a></b><br>{stats}{links}</div>'


def legend():
    return (
        '<p class="rel-legend"><b>depends on</b>: the spec needs the target spec first. '
        "<b>extends</b>: the spec builds on the target spec. Colours: "
        + ", ".join(f'<span class="rel-{group}">{group}</span>' for group in GROUPS)
        + ".</p>"
    )


def relation_table(nodes, edges):
    rows = "".join(
        f"<tr><td>{html.escape(s)}</td><td>{html.escape(label)}</td><td>{html.escape(t)}</td></tr>"
        for s, label, t in edges
    )
    return (
        '<table id="relation-table"><caption>Spec relationships</caption><thead><tr><th>Source</th>'
        f"<th>Label</th><th>Target</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def relation_view(nodes, edges):
    """`nodes` maps spec id to its state counts. Above the cap only the table renders."""
    if len(nodes) > CAP:
        return f"<p>view limited to {CAP} specs; see table</p>" + relation_table(nodes, edges)
    layers = layer_specs(nodes, edges)
    columns = "".join(
        '<div class="rel-col">'
        + "".join(box(s, nodes[s], edges) for s in sorted(nodes) if layers[s] == depth)
        + "</div>"
        for depth in range(max(layers.values(), default=-1) + 1)
    )
    return (
        STYLE
        + f'<div class="rel-view" aria-describedby="relation-table">{columns}</div>'
        + legend()
        + relation_table(nodes, edges)
    )


def relations_panel(snapshot):
    """Body for the sheet panel; edges come from `snapshot['spec_edges']` when present."""
    records = snapshot["records"]
    nodes = {
        r["id"]: state_counts(c["state"] for c in records if c["kind"] == "requirement" and c["parent"] == r["id"])
        for r in records
        if r["kind"] == "spec"
    }
    edges = [tuple(edge) for edge in snapshot.get("spec_edges", []) if edge[0] in nodes and edge[2] in nodes]
    return relation_view(nodes, sorted(edges))
