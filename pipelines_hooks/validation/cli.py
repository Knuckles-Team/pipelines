"""One explicit command for bounded validation and actionable grouped evidence."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.validation.policy import load
from pipelines_hooks.validation.runner import run

PASSIVE = frozenset({"post-merge", "post-checkout", "post-rewrite"})


def _summary(report: dict, path: Path) -> None:
    checks = report["checks"]
    print(f"repository: {len(checks)} checks in {report['seconds']:.3f}s; exit {report['exit_code']}")
    for row in checks:
        if row["outcome"] == "pass":
            continue
        role = "required" if row["required"] else "advisory"
        print(f"  {row['id']}: {row['outcome']} ({role}); {row['remedy']}")
        print(f"    evidence: {row['log']}")
    print(f"report: {path}")


def _run_report(policy, root: Path, args):
    evidence = Path(tempfile.mkdtemp(prefix="pipelines-validation-", dir=args.evidence_dir))
    report = run(policy, root, evidence)
    report["event"] = args.event
    path = evidence / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report, path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pipelines-hook validate", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--event",
        choices=sorted(PASSIVE | {"manual", "pre-commit", "pre-push", "ci"}),
        default="manual",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args(argv)
    if args.event in PASSIVE:
        print(json.dumps({"version": 1, "state": "inactive", "event": args.event, "checks": []}))
        return 0
    root = args.root.resolve()
    policy = load(root / ".config/validation.toml")
    if args.dry_run:
        print(json.dumps({"version": 1, "state": "planned", **asdict(policy)}, sort_keys=True))
        return 0
    try:
        report, path = _run_report(policy, root, args)
    except OSError as exc:
        raise CannotRun(f"validation evidence unavailable: {exc}") from exc
    _summary(report, path)
    return report["exit_code"]


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
