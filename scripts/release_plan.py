"""Render and publish the plan of one release bundle (PIPE-RELEASE-R025.4, R025.5).

The plan lists the rows per repository, the dependency closure, the train order, the scenario and the open tasks. Equal
inputs give equal bytes, and nothing is written to the repository. ``publish_plan`` posts the release graph facts
(ReleaseBundle, inBundle, dependsOn) and the plan to the arbora ``source.*`` operations.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_scope import bundle_closure, train_order  # noqa: E402

DONE = frozenset({"VERIFIED", "RETIRED"})
OPERATION = "source.release_graph"


def render_plan(doc: dict, rows: dict[str, dict]) -> dict:
    """The plan of one manifest. ``train_order`` raises ``BundleCycle`` for a repository cycle."""
    ids = bundle_closure(doc, rows)
    by_repo: dict[str, list[str]] = {}
    for rid in sorted(ids):
        by_repo.setdefault(rows[rid]["repo"], []).append(rid)
    return {
        "release": doc["id"],
        "scenario": doc["scenario"],
        "rows_by_repo": by_repo,
        "closure": sorted(ids),
        "train_order": train_order(ids, rows),
        "open_tasks": sorted(rid for rid in ids if rows[rid].get("status") not in DONE),
    }


def plan_bytes(plan: dict) -> bytes:
    """The canonical bytes of a plan: sorted keys, so equal inputs give equal bytes."""
    return (json.dumps(plan, indent=1, sort_keys=True) + "\n").encode()


def facts_of(plan: dict, rows: dict[str, dict]) -> dict:
    """The release graph facts of one plan."""
    ids = plan["closure"]
    return {
        "ReleaseBundle": [{"id": plan["release"], "scenario": plan["scenario"]}],
        "inBundle": [{"row": rid, "bundle": plan["release"]} for rid in ids],
        "dependsOn": [
            {"row": rid, "on": dep} for rid in ids for dep in rows[rid].get("depends_on", []) if dep in set(ids)
        ],
    }


def _post(endpoint: str, operation: str, params: dict) -> object:
    """Call one served operation through the shared arbora client; ``OSError`` on any refusal."""
    from pipelines_hooks.core.settings import setting
    from pipelines_hooks.verdict_publish import post_operation

    return post_operation(endpoint, setting("PIPELINES_ARBORA_TOKEN"), operation, params)


def publish_plan(facts: dict, plan: dict, endpoint: str, post: Callable[[str, str, dict], object] = _post) -> str:
    """Post the facts and the plan as the served ``source.release_graph`` operation; a refusal raises ``OSError``."""
    if not endpoint:
        return "publish skipped: no endpoint set"
    post(endpoint, OPERATION, {"facts": facts, "plan": plan})
    return f"published {plan['release']}"


def main(argv: list[str] | None = None) -> int:
    """Print the plan of ``--release`` to standard output; a cycle refuses with BUNDLE_CYCLE and exit 1."""
    import argparse

    from scripts.release_scope import RELEASES, BundleCycle, all_rows, load_manifests

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--release", required=True)
    ap.add_argument("--releases", type=Path, default=RELEASES)
    args = ap.parse_args(argv)
    doc = next((d for d in load_manifests(args.releases) if d["id"] == args.release), None)
    if doc is None:
        print(f"no release {args.release}", file=sys.stderr)
        return 2
    try:
        plan = render_plan(doc, all_rows(args.workspace))
    except BundleCycle as exc:
        print(exc, file=sys.stderr)
        return 1
    sys.stdout.buffer.write(plan_bytes(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
