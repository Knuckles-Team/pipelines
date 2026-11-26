"""coverage-decrease: refuse a proposal whose measured test coverage falls below its baseline.

``pipelines-hook coverage-decrease --evidence FILE [--proposal ID] [--root DIR]`` reads one JSON
evidence file::

    {"baseline":  {"percent": "81.50", "revision": "<commit>", "tool": "<tool>"},
     "candidate": {"percent": "82.10", "revision": "<commit>", "tool": "<tool>"}}

Each measurement holds the line-coverage percentage, the revision it measured and the tool that
measured it. The percentage is a measured value with no default. The gate exits 1 when the
candidate is lower than the baseline (exact decimal comparison, so 0.01 points fails) or when the
baseline revision is not an ancestor of the candidate revision, 2 (``CANNOT RUN``) when a
measurement is absent or unreadable, and 0 otherwise. On every verdict it prints one
deterministic evidence line for the caller to keep with the proposal record.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pipelines_hooks.core.baseref import commit
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root, run_git

HUNDRED = Decimal(100)
FIELDS = ("percent", "revision", "tool")


@dataclass(frozen=True)
class CoverageEvidence:
    """One coverage measurement: the percentage, the revision it measured and the tool."""

    percent: Decimal
    revision: str
    tool: str


def _measurement(label: str, raw: object) -> CoverageEvidence:
    if not isinstance(raw, dict):
        raise CannotRun(f"the {label} measurement is absent")
    missing = [name for name in FIELDS if raw.get(name) in (None, "")]
    if missing:
        raise CannotRun(f"the {label} measurement lacks {', '.join(missing)}")
    value = raw["percent"]
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise CannotRun(f"the {label} percent must be a number or a decimal string")
    try:
        percent = Decimal(value)
    except InvalidOperation as exc:
        raise CannotRun(f"the {label} percent {value!r} is not a number") from exc
    if not percent.is_finite() or not Decimal(0) <= percent <= HUNDRED:
        raise CannotRun(f"the {label} percent {value!r} is outside 0 to 100")
    revision, tool = raw["revision"], raw["tool"]
    if not isinstance(revision, str) or not isinstance(tool, str):
        raise CannotRun(f"the {label} revision and tool must be strings")
    return CoverageEvidence(percent=percent, revision=revision, tool=tool)


def parse_evidence(path: Path) -> tuple[CoverageEvidence, CoverageEvidence]:
    """The ``(baseline, candidate)`` measurements of one evidence file."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    except (OSError, UnicodeError, ValueError) as exc:
        raise CannotRun(f"cannot read the evidence file {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise CannotRun(f"the evidence file {path} is not a JSON object")
    return _measurement("baseline", document.get("baseline")), _measurement("candidate", document.get("candidate"))


def compare(baseline: CoverageEvidence, candidate: CoverageEvidence) -> list[str]:
    """One finding naming both percentages when the candidate is lower, else none."""
    if candidate.percent < baseline.percent:
        return [f"coverage fell from {baseline.percent}% to {candidate.percent}%"]
    return []


def render_evidence(proposal_id: str, baseline: CoverageEvidence, candidate: CoverageEvidence) -> str:
    """One evidence line: sorted keys, the same bytes for the same input."""
    record = {
        "baseline_percent": str(baseline.percent),
        "baseline_revision": baseline.revision,
        "candidate_percent": str(candidate.percent),
        "candidate_revision": candidate.revision,
        "proposal": proposal_id,
    }
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def _ancestor_finding(root: Path, baseline: CoverageEvidence, candidate: CoverageEvidence) -> list[str]:
    resolved = {}
    for label, item in (("baseline", baseline), ("candidate", candidate)):
        found = commit(root, item.revision)
        if found is None:
            raise CannotRun(f"the {label} revision {item.revision!r} does not resolve to a commit")
        resolved[label] = found
    result = run_git(root, ("merge-base", "--is-ancestor", resolved["baseline"], resolved["candidate"]))
    if result.returncode == 0:
        return []
    if result.returncode == 1:
        return [
            f"the baseline revision {baseline.revision} is not an ancestor of the candidate revision {candidate.revision}"
        ]
    raise CannotRun(f"git merge-base --is-ancestor failed: {(result.stderr or '').strip()[:200]}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="coverage-decrease", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--evidence", type=Path, help="the JSON evidence file with the baseline and candidate measurements"
    )
    parser.add_argument("--proposal", default="", help="the proposal identity kept in the evidence line")
    args = parser.parse_args(argv)
    if args.evidence is None:
        raise CannotRun("no evidence file: pass --evidence FILE with the baseline and candidate measurements")
    root = repo_root(args.root)
    baseline, candidate = parse_evidence(args.evidence)
    findings = _ancestor_finding(root, baseline, candidate) + compare(baseline, candidate)
    print(render_evidence(args.proposal, baseline, candidate))
    for finding in findings:
        print(f"  - {finding}")
    if findings:
        print("coverage-decrease FAILED.")
        return 1
    print(f"coverage-decrease: OK: {candidate.percent}% is not below the {baseline.percent}% baseline")
    return 0
