"""Organization-level delivery view: priority, frontier, unserved rows, and release bundles.

Recomputes the per-repository scores over every repository's rows, so a cross-repository
Depends-on edge counts. The scorer is shared with the spec-status generator.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines_hooks.specs.priority import Node, bundles, frontier, is_cq, is_functional, score, unserved  # noqa: E402

TOP_BUNDLES = 8


def aggregate(rows: list[dict]) -> dict:
    """Return ``{questions, scores, frontier, unserved, bundles}`` for the given spec rows.

    ``scores`` maps each open row ID to ``{priority, unblocks, cqs}``. ``questions`` lists the competency-question
    rows (ID prefix ``MEDULLA-CQ-``) that at least one other row reaches. ``frontier`` lists open rows with every
    prerequisite done, highest priority first. A prerequisite that no repository declares does not block.
    """
    nodes = {
        r["id"]: Node(
            r["id"],
            r["repo"],
            r["status"],
            tuple(r.get("depends_on", ())),
            is_functional(r.get("spec_id") or r.get("family", "").upper()),
            bool(r.get("rollup", False)),
            r.get("title", ""),
        )
        for r in rows
    }
    scores = score(nodes)
    ready = sorted(frontier(nodes), key=lambda rid: (-scores[rid]["priority"], rid))
    reached = {cq for v in scores.values() for cq in v["cqs"]}
    return {
        "questions": [{"id": rid, "title": nodes[rid].title} for rid in sorted(reached) if is_cq(rid)],
        "scores": scores,
        "frontier": ready,
        "unserved": unserved(nodes, scores),
        "bundles": bundles(nodes, scores)[:TOP_BUNDLES],
    }
