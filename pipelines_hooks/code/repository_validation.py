"""repository-validation: one aggregate verdict over lint, import-order, type and skills.

The aggregate runs ``lint_type.analyze`` once and grades every skill of the same
snapshot once, assembles the shared ``ValidationReport`` and exports it with
``--report-json`` and ``--report-markdown``.  A failing rule is exit 1 whatever
the health score; a required phase that cannot run, a missing grader, a stale
source binding or an escaping skill root is exit 2.  An empty skill inventory is
reported as not applicable together with its checked roots, never as a pass.

Policy lives in ``[tool.pipelines_hooks.repository_validation]``: ``required``
lists the categories whose unavailability is exit 2 (default: all four);
an optional category that cannot run is recorded as a visible skip.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from pipelines_hooks.code import lint_type, repository_health, solution_size
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, repo_root
from pipelines_hooks.core.validation_report import (
    CheckRecord,
    Counts,
    Evidence,
    SkillInventory,
    SkillResult,
    ValidationReport,
)
from pipelines_hooks.docs import skill_grade

CATEGORIES = (*lint_type.PHASES, "skill")


def required_categories(root: Path) -> frozenset[str]:
    raw = blob_bytes(root, ":pyproject.toml")
    try:
        data = tomllib.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"repository-validation: pyproject.toml is unreadable: {exc}") from exc
    table = data.get("tool", {}).get("pipelines_hooks", {}).get("repository_validation", {})
    names = table.get("required", list(CATEGORIES))
    unknown = sorted(set(names) - set(CATEGORIES))
    if unknown:
        raise CannotRun(f"repository-validation: unknown required categories {unknown}")
    return frozenset(names)


def code_checks(root: Path, required: frozenset[str]) -> list[CheckRecord]:
    """The three analyzer phases; an unrunnable analysis yields cannot-run records, not a pass."""
    try:
        records = lint_type.analyze(root)
    except CannotRun as exc:
        records = [
            CheckRecord(category=p, identity=lint_type.TOOL_OF[p], status="cannot-run", status_reason=str(exc))
            for p in lint_type.PHASES
        ]
    return [r.model_copy(update={"required": r.category in required}) for r in records]


def skill_inventory(root: Path, roots: tuple[Path, ...] | None, policy_path: Path | None) -> tuple[SkillInventory, str]:
    """Grade every skill of one snapshot with the standalone grader and bind the results to it."""
    snapshot = skill_grade.select_snapshot(root)
    policy = skill_grade.DEFAULT_POLICY
    if policy_path is not None:
        policy = skill_grade.load_policy(policy_path, snapshot=snapshot)
    declared, documents = skill_grade.discover_skill_inventory(root, roots, snapshot=snapshot)
    relative_roots = tuple(p.relative_to(root).as_posix() or "." for p in declared)
    results = []
    for document in documents:
        graded = skill_grade.grade_document(root, document, policy, snapshot=snapshot)
        if graded.snapshot.get("identity") != snapshot.identity:
            raise CannotRun(f"repository-validation: stale source binding for {graded.skill_path}")
        lineage = tuple(
            f"{e['pack_id']}@{e['pack_version']}:{e['rule_id']}:{e['disposition']}" for e in graded.external_rules
        )
        findings = tuple(
            Evidence(path=f.source_document, line=f.line, observed=f.code, expected=f.criterion, detail=f.message)
            for f in graded.findings
            if f.blocking
        )
        results.append(
            SkillResult(
                skill_path=graded.skill_path,
                snapshot=snapshot.identity,
                skill_digest=graded.source_digest,
                policy_digest=graded.policy_digest,
                status="pass" if graded.status == "pass" else "fail",
                grade=graded.total_grade,
                minimum_grade=graded.minimum_grade,
                criteria=dict(graded.scores),
                lineage=lineage,
                findings=findings,
            )
        )
    if not results:
        reason = "no declared skill documents under the checked roots"
        return SkillInventory(roots=relative_roots, applicable=False, reason=reason), snapshot.identity
    return SkillInventory(roots=relative_roots, results=tuple(results)), snapshot.identity


def collect(
    root: Path,
    roots: tuple[Path, ...] | None = None,
    policy_path: Path | None = None,
    health_policy: Path | None = None,
) -> ValidationReport:
    policy = repository_health.load_policy(health_policy) if health_policy is not None else None
    required = required_categories(root)
    checks = code_checks(root, required) if required & set(lint_type.PHASES) else []
    try:
        skills, identity = skill_inventory(root, roots, policy_path)
    except CannotRun as exc:
        if "skill" in required:
            raise
        skills = SkillInventory(applicable=False, reason=f"skill grading unavailable: {exc}")
        identity = "index"
    summary = None
    if policy is not None:
        phase_counts = {
            c.category: Counts(
                passed=sum(r.outcome == "pass" for r in c.rules),
                failed=sum(r.outcome == "fail" for r in c.rules),
                skipped=int(c.status == "cannot-run"),
            )
            for c in checks
        }
        scored, summary = repository_health.evaluate(root, policy, identity, phase_counts)
        checks = [*checks, *scored]
    return ValidationReport.build(repository=root.name, snapshot=identity, checks=checks, skills=skills, health=summary)


def size_comparison(args: argparse.Namespace) -> int:
    if not (args.size_baseline and args.size_candidate and args.adequacy and args.size_scope):
        raise CannotRun("repository-validation: size comparison needs baseline, candidate, scope and adequacy receipts")
    scope = tuple(args.size_scope)
    result = solution_size.compare(
        solution_size.measure(args.size_baseline, scope),
        solution_size.measure(args.size_candidate, scope),
        solution_size.load_receipts(args.adequacy),
    )
    if args.size_report:
        args.size_report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    delta = result["delta"]
    print(f"repository-validation: size eligible={str(result['eligible']).lower()} delta={delta}")  # type: ignore[index]
    return 0 if result["eligible"] else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="repository-validation", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--skills-root", type=Path, action="append", default=[])
    parser.add_argument("--skill-policy", type=Path)
    parser.add_argument("--health-policy", type=Path, help="score the measured analyzer receipts under this policy")
    parser.add_argument("--size-baseline", type=Path, help="baseline snapshot directory for the size comparison")
    parser.add_argument("--size-candidate", type=Path, help="candidate snapshot directory for the size comparison")
    parser.add_argument("--size-scope", action="append", default=[], help="source directory inside each snapshot")
    parser.add_argument("--adequacy", type=Path, help="adequacy receipts JSON: {receipts: [{id, snapshot, behavior}]}")
    parser.add_argument("--size-report", type=Path)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-markdown", type=Path)
    args = parser.parse_args(argv)
    if args.size_baseline or args.size_candidate:
        return size_comparison(args)
    root = repo_root(args.root)
    report = collect(
        root,
        tuple(args.skills_root) or None,
        args.skill_policy,
        root / args.health_policy if args.health_policy else None,
    )
    if args.report_json:
        args.report_json.write_text(report.to_json() + "\n", encoding="utf-8")
    if args.report_markdown:
        args.report_markdown.write_text(report.to_markdown(), encoding="utf-8")
    print(f"repository-validation: verdict={report.verdict} full_coverage={str(report.full_coverage).lower()}")
    for name, counts in report.counts.items():
        print(f"  {name}: pass={counts.passed} fail={counts.failed} skip={counts.skipped}")
    for check in report.checks:
        if check.status_reason:
            print(f"  {check.category}: cannot run: {check.status_reason}")
        for rule in check.rules:
            for item in rule.evidence if rule.outcome == "fail" else ():
                print(f"  {check.category}: {item.path}:{item.line} {rule.rule} {item.detail}")
    if report.health is not None:
        health = report.health
        print(
            f"  health: score={health.score if health.score_available else 'unavailable'} coverage={health.coverage:g}"
        )
        for fix in health.fixes:
            print(f"  fix {fix.rank}: {fix.category} {fix.rule} {fix.path}:{fix.line or 1} {fix.severity}")
    if report.skills is not None:
        if not report.skills.applicable:
            print(
                f"  skill: not applicable ({report.skills.reason}); roots: {', '.join(report.skills.roots) or 'none'}"
            )
        for result in report.skills.results:
            print(f"  skill: {result.skill_path} {result.status} grade={result.grade} lineage={list(result.lineage)}")
            for item in result.findings:
                print(f"    {item.path}:{item.line} {item.observed} {item.detail}")
    if report.verdict == "cannot-run":
        raise CannotRun("repository-validation: a required check could not run")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
