"""``release_orchestrator.py <command> ...``: the dependency-ordered release CLI.

Every command reads local JSON files and never reaches a network or a hosted
credential (FR-5, portable execution): a contributor runs ``validate``,
``plan``, ``publish``, and ``verify-consumers`` from public fixtures alone.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from pipelines_hooks.core.bounded_json import read_bounded_json

from .candidate import candidate_set_errors, parse_candidate_set
from .digest_handoff import verify_consumer_manifest
from .errors import ReleaseError
from .models import CheckResult, ReleaseRun, StageOutcome
from .ordering import topological_order
from .orchestrator import RecordedPublisher, orchestrate
from .qualification import RecordedChecksClient, qualify
from .receipts import FileReceiptStore
from .reproducibility import build_wheel_twice, compare_wheels

_MAX_INPUT_BYTES = 2_000_000


def _load(path: str) -> object:
    return read_bounded_json(Path(path), _MAX_INPUT_BYTES, what=path, error=ReleaseError)


def _checks_client(path: str) -> RecordedChecksClient:
    raw = _load(path)
    recorded = {
        (row["repository"], row["commit"]): tuple(CheckResult(**item) for item in row["results"])
        for row in raw
    }
    return RecordedChecksClient(recorded)


def _main_validate(args: argparse.Namespace) -> int:
    raw = _load(args.manifest)
    errors = candidate_set_errors(raw.get("candidates", []))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"candidate set is valid: {len(raw.get('candidates', []))} candidates")
    return 0


def _main_plan(args: argparse.Namespace) -> int:
    candidates = parse_candidate_set(_load(args.manifest))
    order = topological_order(candidates)
    qualification = qualify(candidates, order, _checks_client(args.checks))
    for component_id in order:
        state = "eligible" if component_id in qualification.eligible else f"blocked: {qualification.blocked[component_id]}"
        print(f"{component_id}: {state}")
    return 0 if not qualification.blocked else 1


def _main_publish(args: argparse.Namespace) -> int:
    candidates = parse_candidate_set(_load(args.manifest))
    order = topological_order(candidates)
    plan = {row["component_id"]: StageOutcome(**row) for row in _load(args.plan)}
    run = orchestrate(
        candidates,
        order,
        checks=_checks_client(args.checks),
        publisher=RecordedPublisher(plan),
        receipts=FileReceiptStore(Path(args.receipts)),
    )
    failures = [o for o in run.outcomes if o.status != "published"]
    for outcome in run.outcomes:
        print(f"{outcome.component_id}: {outcome.status} ({outcome.reason or outcome.artifact_digest})")
    return 0 if not failures else 1


def _main_verify_consumers(args: argparse.Namespace) -> int:
    plan = {row["component_id"]: StageOutcome(**row) for row in _load(args.plan)}
    run = ReleaseRun(set_digest="", outcomes=tuple(plan.values()))
    problems = verify_consumer_manifest(run, dict(_load(args.consumers)))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("every declared workload reference matches the qualified digest mapping")
    return 0


def _main_check_reproducible_build(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as workdir:
        wheel_a, wheel_b = build_wheel_twice(
            Path(args.source), Path(workdir) / "build-a", Path(workdir) / "build-b", source_date_epoch=args.epoch
        )
        result = compare_wheels(wheel_a, wheel_b)
    if not result.identical:
        print("\n".join(result.differences), file=sys.stderr)
        return 1
    print(f"{wheel_a.name} is byte-identical across two independent builds")
    return 0


_COMMANDS = {
    "validate": (_main_validate, ("manifest",)),
    "plan": (_main_plan, ("manifest", "checks")),
    "publish": (_main_publish, ("manifest", "checks", "plan", "receipts")),
    "verify-consumers": (_main_verify_consumers, ("plan", "consumers")),
    "check-reproducible-build": (_main_check_reproducible_build, ("source", "epoch")),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, (_, arguments) in _COMMANDS.items():
        subparser = subparsers.add_parser(name)
        for argument in arguments:
            subparser.add_argument(f"--{argument}", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handler, _ = _COMMANDS[args.command]
    try:
        return handler(args)
    except ReleaseError as exc:
        print(f"CANNOT RUN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
