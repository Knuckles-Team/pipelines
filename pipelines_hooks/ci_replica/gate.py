"""ci-gate-replica entry point: ``--consistency-check``, ``--dry-run``, ``--skip-safe [REF]``, or a full run."""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from pipelines_hooks.ci_replica import execute
from pipelines_hooks.ci_replica.consistency import build_affecting_changes, consistency_problems
from pipelines_hooks.ci_replica.plan import build_plan, load_workflow
from pipelines_hooks.ci_replica.registry import load_registry
from pipelines_hooks.core.gitenv import repo_root


def _skip_safe(root: Path, base_ref: str, patterns: tuple[str, ...]) -> int:
    hits = build_affecting_changes(root, base_ref=base_ref, patterns=patterns)
    if not hits:
        print(f"SKIP-SAFE: no build-affecting files changed vs {base_ref!r}")
        return 0
    print(f"NOT SKIP-SAFE: build-affecting file(s) changed vs {base_ref!r}:\n" + "\n".join(f"  - {h}" for h in hits))
    return 1


def _row_status(row: dict, *, root: Path, dry_run: bool, environments: dict) -> object:
    if row["mode"] != "RUN":
        if row["mode"] == "SKIP_LOUD":
            print(f"\n### NOT VALIDATED LOCALLY [{row['workflow']}:{row['job']}] {row['name']}\n    reason: {row['detail']}")
        return {"ENV_SETUP": "ENV_SETUP", "ARTIFACT_IO": "ARTIFACT_IO"}.get(row["mode"], "NOT_VALIDATED_LOCALLY")
    if dry_run:
        print(f"[DRY-RUN] would RUN [{row['workflow']}:{row['job']}] {row['name']}")
        return "DRY_RUN"
    print(f"\n############### STEP [{row['workflow']}:{row['job']}] {row['name']} ###############")
    status, elapsed = execute.run_step(row["detail"], root=root, environment=environments[(row["workflow"], row["job"])])
    print(f"### STEP_RESULT job={row['job']} name={row['name']!r} exit={status} secs={elapsed:.1f}")
    return status


def _summary(results: list[tuple[dict, object]]) -> int:
    print("\n################ SUMMARY ################")
    for row, status in results:
        print(f"{row['workflow'] + ':' + row['job']:36s} {row['name'][:56]:56s} status={status}")
    failures = [row["blocking"] for row, status in results if execute.failed(status)]
    print(f"BLOCKING_FAIL={int(any(failures))}\nADVISORY_FAIL={int(not all(failures) if failures else 0)} (reported, never fails the gate)")
    return 1 if any(failures) else 0


def replay(root: Path, *, workflows_dir: Path, dry_run: bool) -> int:
    registry, _ = load_registry(root)
    documents = {name: load_workflow(workflows_dir / name) for name in registry}
    plan = [row for name, spec in registry.items() for row in build_plan(spec, documents[name])[0]]
    environments = {(r["workflow"], r["job"]): execute.job_environment(documents[r["workflow"]], r["job"].split("#", 1)[0]) for r in plan}
    if not dry_run:
        execute.local_hygiene(root)
    print(f"=== ci-gate-replica START {datetime.datetime.now(datetime.UTC).isoformat()} ===")
    return _summary([(row, _row_status(row, root=root, dry_run=dry_run, environments=environments)) for row in plan])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ci-gate-replica", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--consistency-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-safe", nargs="?", const="HEAD", metavar="BASE_REF")
    parser.add_argument("--workflows-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    registry, patterns = load_registry(root)
    if args.skip_safe is not None:
        return _skip_safe(root, args.skip_safe, patterns)
    workflows_dir = args.workflows_dir or root / ".github" / "workflows"
    problems = consistency_problems(root, workflows_dir=workflows_dir, registry=registry)
    for problem in problems:
        print(f"CONSISTENCY CHECK FAILED: {problem}")
    if problems or args.consistency_check:
        return 1 if problems else 0
    return replay(root, workflows_dir=workflows_dir, dry_run=args.dry_run)
