"""public-surface: the README (and AGENTS.md when present) point at things that exist.

The gate checks only what breaks for a reader: a missing README, a relative
link or image whose target is absent or outside the repository, a link with a
non-web URL scheme, and a README that never says how to install or start the
project. Wording, length and section layout are review matters, not gates.
The gate is offline: web links are not fetched.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.bounded_json import read_bounded_json
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.docs.claims import (
    FindingRefusal,
    LocatedFinding,
    claim_findings,
    collect_claims,
    document_sources,
    export_located_evidence,
    load_located_evidence,
    parse_claims,
    validate_located_evidence,
)
from pipelines_hooks.docs.public_surface_links import local_link_findings
from pipelines_hooks.docs.public_surface_quickstart import findings as quick_start_findings


def _read(root: Path, name: str) -> str | None:
    path = root / name
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"cannot read {name}: {exc}") from exc


def validate(
    root: Path,
    *,
    report: dict[str, int] | None = None,
    located_findings: list[LocatedFinding] | None = None,
    refusals: list[FindingRefusal] | None = None,
    persisted_findings: list[LocatedFinding] | None = None,
) -> list[str]:
    """Return all public-surface findings for ``root``.

    Explicit claims are collected from the root README, optional ``AGENTS.md``
    and the policy-scoped documentation inventory.  ``report`` is an internal
    summary seam for the CLI; the ordinary return value remains the existing
    list of strings used by callers.
    """
    if located_findings is not None and refusals is None:
        refusals = []
    readme = _read(root, "README.md")
    if readme is None:
        if report is not None:
            report.update(checked=0, unresolved=0)
        return ["README.md is required"]
    findings = quick_start_findings(readme) + local_link_findings(root, readme, name="README.md")
    claims = parse_claims(readme, file="README.md")
    agents = _read(root, "AGENTS.md")
    if agents is not None:
        findings += local_link_findings(root, agents, name="AGENTS.md")
        claims.extend(parse_claims(agents, file="AGENTS.md"))
    sources = document_sources(root)
    claims = collect_claims(root, claims, sources=sources)
    for path, text in sources:
        relative = path.relative_to(root).as_posix()
        if relative not in {"README.md", "AGENTS.md"}:
            findings += local_link_findings(root, text, name=relative, base=path.parent)
    if persisted_findings is not None:
        claim_results = []
        for finding in persisted_findings:
            refusal = validate_located_evidence(root, finding, measured=finding.observed)
            if refusal is not None:
                if refusals is not None:
                    refusals.append(refusal)
                continue
            if located_findings is not None:
                located_findings.append(finding)
            if finding.observed != finding.expected:
                record = finding.as_dict()
                claim_results.append(f"{record['source_path']}:{record['line']} {record['rule']}")
    elif located_findings is None:
        claim_results = claim_findings(root, claims)
    else:
        claim_results = claim_findings(root, claims, located_findings=located_findings, refusals=refusals)
    if refusals:
        detail = "; ".join(
            f"{record['source_path']}:{record['line']} {record['reason']}"
            for record in (refusal.as_dict() for refusal in refusals)
        )
        raise CannotRun(f"located-evidence unsupported-finding: {detail}")
    claim_stats = {"checked": len(claims), "unresolved": len(claim_results)}
    findings += claim_results
    if report is not None:
        report.update(claim_stats)
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="public-surface", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--evidence",
        type=Path,
        help="validate persisted located-evidence JSON against the current scanned tree",
    )
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    report: dict[str, int] = {}
    located_findings: list[LocatedFinding] = []
    refusals: list[FindingRefusal] = []
    persisted_findings: list[LocatedFinding] | None = None
    if args.evidence is not None:
        try:
            payload = read_bounded_json(args.evidence, 2 * 1024 * 1024, what="located-evidence input", error=CannotRun)
        except OSError as exc:
            raise CannotRun(f"located-evidence input cannot be read: {exc}") from exc
        persisted_findings, persisted_refusals = load_located_evidence(payload)
        refusals.extend(persisted_refusals)
    findings = validate(
        root,
        report=report,
        located_findings=located_findings,
        refusals=refusals,
        persisted_findings=persisted_findings,
    )
    print(f"claims: checked {report.get('checked', 0)}, unresolved {report.get('unresolved', 0)}")
    if located_findings:
        print(f"located-evidence: {export_located_evidence(located_findings)}")
    if not findings:
        print("public surface: clean")
        return 0
    print("FAIL: public README/AGENTS surface.")
    for finding in findings:
        print(f"  - {finding}")
    return 1
