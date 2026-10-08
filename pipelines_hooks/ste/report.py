"""Shared report for the ste gates: sorted findings, stable exit code.

Exit 0 when there is no failing finding (advisory findings still print);
exit 1 when at least one failing finding exists.
"""

from __future__ import annotations

from pipelines_hooks.ste.scan import Finding

ADVICE = """
Split sentences that run over the cap. Replace banned words with the fix each
finding names. Name the actor and use the active voice. State a measured value
or mark an estimate measured: ~N. Pick one term per concept from its cluster.
Do NOT raise a threshold and do NOT add a suppression comment -- an in-line
suppression is a one-line baseline; fix the prose.
"""


def report(gate: str, findings: list[Finding]) -> int:
    """Print the findings; return the gate exit code."""
    ordered = sorted(findings, key=lambda f: (f.path, f.line, f.code, f.message))
    for finding in ordered:
        tag = "ADV " if finding.advisory else ""
        print(f"{tag}{finding.path}:{finding.line}: [{finding.code}] {finding.message}")
    failing = sum(1 for finding in ordered if not finding.advisory)
    if not ordered:
        print(f"{gate}: OK: no findings")
    elif failing:
        print(f"\n{gate}: FAIL: {failing} finding(s), {len(ordered) - failing} advisory")
        print(ADVICE)
        return 1
    else:
        print(f"\n{gate}: OK: 0 finding(s), {len(ordered)} advisory")
    return 0
