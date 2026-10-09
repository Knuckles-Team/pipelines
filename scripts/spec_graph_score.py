"""Size scoring and mechanical split proposals (sections 2 and 3 of
``plans/refactor/reconciliation-20261006/SPEC-SIZING-AND-DEPENDENCIES.md``).
"""

from __future__ import annotations

import re

if __package__:
    from .spec_graph_core import LANDED_STATES, SPLIT_THRESHOLD, Requirement
else:
    from spec_graph_core import LANDED_STATES, SPLIT_THRESHOLD, Requirement


def verification_clauses(text: str) -> int:
    if not text.strip():
        return 0
    parts = [part for part in re.split(r"(?<=[.;])\s+", text.strip()) if part.strip()]
    return max(1, len(parts))


def size_breakdown(req: Requirement, delivery_states: dict[str, str]) -> dict[str, int]:
    unresolved_deps = sum(
        1
        for dep in req.depends_on
        if delivery_states.get(dep, "UNKNOWN") not in LANDED_STATES
    )
    return {
        "unchecked_tasks": req.unchecked_tasks,
        "verification_clauses": verification_clauses(req.verification_text)
        + req.test_mentions,
        "extra_code_roots": max(0, len(req.code_roots) - 1),
        "other_repos": len(req.other_repos),
        "unresolved_deps": unresolved_deps,
    }


def size_score(req: Requirement, delivery_states: dict[str, str]) -> int:
    breakdown = size_breakdown(req, delivery_states)
    return (
        breakdown["unchecked_tasks"]
        + breakdown["verification_clauses"]
        + breakdown["extra_code_roots"] * 2
        + breakdown["other_repos"] * 3
        + breakdown["unresolved_deps"] * 2
    )


def needs_split(req: Requirement, score: int) -> bool:
    return score > SPLIT_THRESHOLD or len(req.code_roots) > 2 or bool(req.other_repos)


def propose_split(req: Requirement) -> tuple[str, list[tuple[str, str]]]:
    """One child per code root (or per repository, if cross-repo), in
    dependency order (producer before consumer, approximated here as the
    owning repo first, then other repos alphabetically). A requirement whose
    oversized score names neither multiple code roots nor another repository
    falls back to a generic two-way split, flagged for manual re-splitting."""
    if len(req.code_roots) >= 2:
        parts = sorted(req.code_roots)
        basis = "code_root"
    elif req.other_repos:
        parts = [req.repo] + sorted(req.other_repos)
        basis = "repo"
    else:
        parts = ["part-1", "part-2"]
        basis = "fallback"
    children = [
        (f"{req.id}.{index}", part) for index, part in enumerate(parts, start=1)
    ]
    return basis, children


def proposed_splits(reqs: dict[str, Requirement]) -> list[dict[str, object]]:
    delivery_states = {rid: req.delivery_state for rid, req in reqs.items()}
    out = []
    for rid, req in sorted(reqs.items()):
        if req.delivery_state in LANDED_STATES:
            continue
        score = size_score(req, delivery_states)
        if not needs_split(req, score):
            continue
        basis, children = propose_split(req)
        out.append(
            {
                "id": rid,
                "score": score,
                "basis": basis,
                "children": [{"id": cid, "scope": scope} for cid, scope in children],
            }
        )
    return out
