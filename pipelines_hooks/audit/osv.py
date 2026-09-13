"""Query OSV for every pinned package and resolve each advisory's fixed versions."""

from __future__ import annotations

from typing import Any

from pipelines_hooks.audit.acceptances import ADVISORY_RE
from pipelines_hooks.audit.lock import AuditError, normalise_package
from pipelines_hooks.audit.osv_client import OSV_BATCH, OSV_VULN_PREFIX, request

Finding = tuple[str, str, str, tuple[str, ...]]
BATCH_SIZE = 100


def _names_package(affected: object, package: str) -> bool:
    identity = affected.get("package") if isinstance(affected, dict) else None
    return isinstance(identity, dict) and normalise_package(str(identity.get("name") or "")) == package


def _range_fixed(version_range: object) -> set[str]:
    events = version_range.get("events") if isinstance(version_range, dict) else None
    return {e["fixed"] for e in events or [] if isinstance(e, dict) and isinstance(e.get("fixed"), str)}


def _fixed_versions(affected: object, package: str) -> set[str]:
    if not _names_package(affected, package):
        return set()
    return {fixed for version_range in affected.get("ranges") or [] for fixed in _range_fixed(version_range)}


def advisory_fixed_versions(advisory_id: str, package: str) -> tuple[str, ...]:
    detail = request(OSV_VULN_PREFIX + advisory_id)
    return tuple(sorted({v for affected in detail.get("affected") or [] for v in _fixed_versions(affected, package)}))


def _result_findings(pair: tuple[str, str], result: object) -> list[Finding]:
    if not isinstance(result, dict):
        raise AuditError("OSV batch response is invalid")
    findings = []
    for vulnerability in result.get("vulns") or []:
        advisory = vulnerability.get("id") if isinstance(vulnerability, dict) else None
        if not isinstance(advisory, str) or not ADVISORY_RE.fullmatch(advisory):
            raise AuditError("OSV advisory identity is invalid")
        findings.append((pair[0], pair[1], advisory, advisory_fixed_versions(advisory, pair[0])))
    return findings


def _batch(chunk: list[tuple[str, str]]) -> list[Any]:
    queries = [{"package": {"name": name, "ecosystem": "PyPI"}, "version": version} for name, version in chunk]
    results = request(OSV_BATCH, payload={"queries": queries}).get("results")
    if not isinstance(results, list) or len(results) != len(chunk):
        raise AuditError("OSV batch response does not match the request")
    return results


def audit(packages: tuple[tuple[str, str], ...]) -> list[Finding]:
    """Every advisory against every pinned package."""
    selections = sorted(packages)
    findings: list[Finding] = []
    for offset in range(0, len(selections), BATCH_SIZE):
        chunk = selections[offset : offset + BATCH_SIZE]
        for pair, result in zip(chunk, _batch(chunk), strict=True):
            findings.extend(_result_findings(pair, result))
    return findings
