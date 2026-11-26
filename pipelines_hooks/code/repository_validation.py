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
import hashlib
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path, PurePosixPath

from pipelines_hooks.code import lint_type, repository_health, solution_size
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, blob_text, git_text, nul_split, repo_root
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


# --- skill dependency audit (PIPE-PAGES-R021.31 to R021.36) -----------------------------------------
# A skill declares its dependencies in ``requirements.txt`` beside its ``SKILL.md``: one ``name==version``
# per line, grouped by ``# group: <name>`` headings. The audit reads the Git bytes, joins them with a pinned
# advisory snapshot and files one update proposal per vulnerable dependency with the owner's proposal store.
# It never installs, never edits a lock and never applies a proposal; approval is a separate, later consumer.

_PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)$")
_GROUP = re.compile(r"^#\s*group:\s*(\S+)\s*$")
ADVISORY_MAX_AGE_DAYS = 7


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class SkillDependencyAudit:
    """One skill's declared dependencies, the advisories that hit them and the proposals filed for them."""

    skill_path: str
    skill_digest: str
    inventory_digest: str
    groups: dict[str, tuple[tuple[str, str], ...]]
    advisory_digest: str
    findings: tuple[dict, ...] = ()
    proposals: tuple[dict, ...] = field(default=())
    receipts: tuple[dict, ...] = field(default=())
    approval_state: str = "unapproved"  # kept apart from the audit result; a consumer changes it, never the audit
    installation_effects: int = 0  # the audit path installs nothing, so a suggestion is never applied remediation

    def evidence(self) -> dict:
        return {
            "gate": "repository-validation",
            "audit": "skill-dependencies",
            "skill": self.skill_path,
            "skill_digest": self.skill_digest,
            "inventory_digest": self.inventory_digest,
            "advisory_digest": self.advisory_digest,
            "findings": list(self.findings),
            "proposals": [p["identity"] for p in self.proposals],
            "receipts": list(self.receipts),
            "approval_state": self.approval_state,
            "installation_effects": self.installation_effects,
        }


def parse_declaration(skill_path: str, text: str | None) -> dict[str, tuple[tuple[str, str], ...]]:
    """The dependency groups of one declaration; a missing declaration or an unpinned line cannot be audited."""
    if text is None:
        raise CannotRun(f"repository-validation: {skill_path} has no dependency declaration (requirements.txt)")
    groups: dict[str, list[tuple[str, str]]] = {}
    group = "default"
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        heading = _GROUP.match(line)
        if heading:
            group = heading.group(1)
        elif line and not line.startswith("#"):
            pin = _PIN.match(line)
            if pin is None:
                raise CannotRun(f"repository-validation: {skill_path}:{number} version is unresolved: {line!r}")
            groups.setdefault(group, []).append((pin.group(1).lower(), pin.group(2)))
    return {g: tuple(sorted(pins)) for g, pins in sorted(groups.items())}


def read_advisories(path: Path, as_of: date) -> tuple[list[dict], str]:
    """The pinned advisory snapshot and its digest; evidence older than the allowed age cannot be trusted."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        captured = date.fromisoformat(document["captured_at"])
        advisories = list(document["advisories"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CannotRun(f"repository-validation: advisory snapshot {path} is unreadable: {exc}") from exc
    if (as_of - captured).days > ADVISORY_MAX_AGE_DAYS:
        raise CannotRun(f"repository-validation: advisory snapshot is stale (captured {captured}, as of {as_of})")
    return advisories, _digest(document)


def _hits(groups: dict, advisories: list[dict]) -> list[dict]:
    hits = []
    for group, pins in groups.items():
        for name, version in pins:
            for advisory in advisories:
                if advisory["package"].lower() == name and version in advisory["affected"]:
                    hits.append(
                        {
                            "advisory": advisory["id"],
                            "group": group,
                            "package": name,
                            "version": version,
                            "target": advisory["fixed"],
                        }
                    )
    return hits


class ProposalStore:
    """The owner's proposal storage as a directory of identity-keyed records (the served adapter has this shape)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def put(self, proposal: dict) -> dict:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / f"{proposal['identity']}.json").write_text(json.dumps(proposal, sort_keys=True))
        except OSError as exc:
            raise CannotRun(f"repository-validation: owner proposal storage is unavailable: {exc}") from exc
        return {"identity": proposal["identity"], "stored": True}

    def get(self, identity: str) -> dict | None:
        path = self.directory / f"{identity}.json"
        return json.loads(path.read_text()) if path.is_file() else None


def audit_skill(
    skill_path: str, text: str | None, advisories: list[dict], advisory_digest: str, store: ProposalStore | None
):
    """Audit one skill: findings always, proposals only through the store, storage failure after the findings."""
    groups = parse_declaration(skill_path, text)
    skill_digest = _digest(text)
    inventory_digest = _digest({g: [list(p) for p in pins] for g, pins in groups.items()})
    findings = tuple(_hits(groups, advisories))
    proposals = tuple(
        {
            "identity": _digest([skill_path, skill_digest, hit["advisory"], hit["package"], hit["target"]]),
            "skill": skill_path,
            "old": hit["version"],
            "target": hit["target"],
            "finding": hit["advisory"],
            "package": hit["package"],
            "provenance": {
                "skill_digest": skill_digest,
                "inventory_digest": inventory_digest,
                "advisory": advisory_digest,
            },
            "artifact_digest": skill_digest,
        }
        for hit in findings
    )
    audit = SkillDependencyAudit(
        skill_path, skill_digest, inventory_digest, groups, advisory_digest, findings, proposals
    )
    if not proposals:
        return audit
    if store is None:
        raise CannotRun("repository-validation: owner proposal storage is unavailable (no --proposal-store)")
    try:
        receipts = tuple(store.put(p) for p in proposals)
        if any(store.get(p["identity"]) != p for p in proposals):  # independent readback
            raise CannotRun("repository-validation: stored proposal differs on readback")
    except CannotRun:
        print(json.dumps(audit.evidence(), sort_keys=True))  # the vulnerability stays a finding
        raise
    return replace(audit, receipts=receipts)


def bind_approval(store: ProposalStore, identity: str, artifact_digest: str) -> dict:
    """The separate consumer's check: an approval binds one stored proposal and its exact artifact digest."""
    proposal = store.get(identity)
    if proposal is None or proposal["artifact_digest"] != artifact_digest:
        raise CannotRun("repository-validation: the approval is stale or names no stored proposal")
    return {"identity": identity, "artifact_digest": artifact_digest, "approval_state": "approved"}


def audit_skill_dependencies(root: Path, advisory_path: Path, store: ProposalStore | None, as_of: date) -> int:
    """Audit every skill of the snapshot; exit 1 when any dependency is vulnerable."""
    advisories, advisory_digest = read_advisories(advisory_path, as_of)
    skills = [p for p in nul_split(git_text(root, ("ls-files", "-z", "--", "*SKILL.md"), preserve_index=True))]
    status = 0
    for skill in sorted(skills):
        declaration = blob_text(root, f":{PurePosixPath(skill).parent.as_posix()}/requirements.txt")
        audit = audit_skill(skill, declaration, advisories, advisory_digest, store)
        print(json.dumps(audit.evidence(), sort_keys=True))
        status = 1 if audit.findings else status
    return status


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
    parser.add_argument("--audit-skill-dependencies", type=Path, metavar="ADVISORIES", help="pinned advisory snapshot")
    parser.add_argument("--proposal-store", type=Path, help="owner proposal storage directory")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="date the advisory age is judged at")
    parser.add_argument("--install", action="store_true", help="refused: the audit path never installs")
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-markdown", type=Path)
    args = parser.parse_args(argv)
    if args.size_baseline or args.size_candidate:
        return size_comparison(args)
    root = repo_root(args.root)
    if args.install:
        raise CannotRun(
            "repository-validation: the audit path never installs packages, edits locks or applies a proposal"
        )
    if args.audit_skill_dependencies:
        store = ProposalStore(args.proposal_store) if args.proposal_store else None
        return audit_skill_dependencies(root, args.audit_skill_dependencies, store, args.as_of or date.today())
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
