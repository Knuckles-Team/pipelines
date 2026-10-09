"""Deterministic spec dependency graph, sizing and mechanical splitting.

Implements the rules in
``plans/refactor/reconciliation-20261006/SPEC-SIZING-AND-DEPENDENCIES.md``:
reads only ``specs/*/{spec.md,requirements.md,tasks.md,test-spec.md,status.json}``
and the repository tree, so two runs on the same commit give the same answer.

Prints, for one or more repository roots:

1. dependency edges (cross-repo included)
2. the UNBLOCKED frontier per repo, ordered by transitive-dependents count
   (highest first) then size score (smallest first)
3. the size score per open requirement
4. proposed mechanical splits for requirements over the threshold

``--write --repo <root> --req <ID>`` applies one proposed split to that
repository's spec files.

The model, per-file-type parsers, scoring and the ``--write`` path live in the
sibling ``scripts/spec_graph_*.py`` modules; this file is the CLI and the
single public import surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__:
    from .spec_graph_frontier import dependency_edges, frontier, is_open
    from .spec_graph_load import load_repo, load_repos
    from .spec_graph_score import (
        needs_split,
        propose_split,
        proposed_splits,
        size_breakdown,
        size_score,
    )
    from .spec_graph_write import apply_split
else:
    from spec_graph_frontier import dependency_edges, frontier, is_open
    from spec_graph_load import load_repo, load_repos
    from spec_graph_score import (
        needs_split,
        propose_split,
        proposed_splits,
        size_breakdown,
        size_score,
    )
    from spec_graph_write import apply_split

__all__ = [
    "apply_split",
    "dependency_edges",
    "frontier",
    "load_repo",
    "load_repos",
    "needs_split",
    "propose_split",
    "proposed_splits",
    "size_breakdown",
    "size_score",
]


def _report(reqs: dict) -> dict[str, object]:
    delivery_states = {rid: req.delivery_state for rid, req in reqs.items()}
    return {
        "edges": [{"from": a, "to": b} for a, b in dependency_edges(reqs)],
        "frontier": frontier(reqs),
        "scores": {
            rid: {
                "score": size_score(req, delivery_states),
                **size_breakdown(req, delivery_states),
            }
            for rid, req in sorted(reqs.items())
            if is_open(req)
        },
        "splits": proposed_splits(reqs),
    }


def _print_text(report: dict[str, object]) -> None:
    print("## Dependency edges")
    for edge in report["edges"]:
        print(f"{edge['from']} -> {edge['to']}")
    print("\n## Unblocked frontier (per repo, highest dependents first)")
    for repo, rows in sorted(report["frontier"].items()):
        print(f"### {repo}")
        for row in rows:
            print(
                f"  {row['id']}  dependents={row['dependents']}  score={row['score']}"
            )
    print("\n## Size scores (open requirements)")
    for rid, breakdown in report["scores"].items():
        print(f"{rid}: score={breakdown['score']} {breakdown}")
    print("\n## Proposed splits (score > 6, > 2 code roots, or cross-repo)")
    for split in report["splits"]:
        children = ", ".join(child["id"] for child in split["children"])
        print(
            f"{split['id']} (score={split['score']}, basis={split['basis']}) -> {children}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", help="one or more repository roots")
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    parser.add_argument("--write", action="store_true", help="apply one proposed split")
    parser.add_argument("--repo", help="repository root to write into")
    parser.add_argument("--req", help="requirement ID to split")
    args = parser.parse_args(argv)

    if args.write:
        if not args.repo or not args.req:
            parser.error("--write requires --repo and --req")
        child_ids = apply_split(Path(args.repo), args.req)
        print(f"{args.req}: split into {', '.join(child_ids)}")
        return 0

    if not args.roots:
        parser.error("at least one repository root is required")
    reqs = load_repos([Path(root) for root in args.roots])
    report = _report(reqs)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
