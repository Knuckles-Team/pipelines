"""dependency-audit gate: OSV findings against the risk-acceptance ledger."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipelines_hooks.audit.acceptances import RiskAcceptance, load_acceptances
from pipelines_hooks.audit.lock import AuditError, parse_lock
from pipelines_hooks.audit.osv import Finding, audit
from pipelines_hooks.audit.osv_client import UNAVAILABLE
from pipelines_hooks.core.settings import setting


def classify(findings: list[Finding], acceptances: dict[tuple[str, str], RiskAcceptance]) -> tuple[list[Finding], set[tuple[str, str]]]:
    """``(unaccepted failures, used acceptance keys)``, printing each finding."""
    failures, used = [], set()
    for name, version, advisory, fixed in sorted(findings):
        key = (advisory.casefold(), name)
        if key in acceptances:
            used.add(key)
            print(f"  ACCEPTED {name} {version} {advisory} until {acceptances[key].expires.isoformat()}")
            continue
        failures.append((name, version, advisory, fixed))
        print(f"  FAIL {name} {version} {advisory} fixed={','.join(fixed) if fixed else 'no-fixed-release'}")
    return failures, used


def _verdict(lock: Path) -> int:
    packages = parse_lock(lock)
    acceptances = load_acceptances(lock.resolve().parent)
    findings = audit(packages)
    failures, used = classify(findings, acceptances)
    stale = sorted(set(acceptances) - used)
    for advisory, package in stale:
        print(f"  FAIL stale acceptance {package} {advisory}")
    if failures or stale:
        print("audit: dependency vulnerabilities or stale risk acceptances require review", file=sys.stderr)
        return 1
    print(f"audit: clean ({len(packages)} pinned packages, {len(findings)} findings)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dependency-audit")
    parser.add_argument("lock", nargs="?", type=Path, default=Path("uv.lock"))
    lock = parser.parse_args(argv).lock
    try:
        return _verdict(lock)
    except AuditError as error:
        if str(error) == UNAVAILABLE and setting("SECURITY_AUDIT_OFFLINE_POLICY").casefold() == "warn":
            print("audit: WARNING - OSV unavailable under explicit local offline policy")
            return 0
        print(f"audit: FAILED - {error}", file=sys.stderr)
        return 2
