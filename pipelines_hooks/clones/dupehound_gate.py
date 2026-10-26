"""dupehound-changed: no changed function may structurally reimplement an existing one.

Without ``--base-ref`` dupehound compares the staged index against HEAD (the
pre-commit form); with ``--base-ref`` (or ``CX_DUP_BASE_REF``) it compares a
commit range (the CI form). Test paths are skipped by dupehound itself, so a
test-only change reports as outside this gate rather than as clean.
"""

from __future__ import annotations

from typing import Any

from pipelines_hooks.clones import dupehound, dupehound_report, ledger
from pipelines_hooks.clones.contract import DUPEHOUND_DIAGNOSTIC_THRESHOLD, DUPEHOUND_THRESHOLD
from pipelines_hooks.core.args import root_and_base_ref
from pipelines_hooks.core.settings import setting
from pipelines_hooks.core.tools import verified


def _print_findings(findings: list[dict[str, Any]]) -> None:
    for finding in findings:
        print(
            f"  {finding['file']}:{finding['line']} {finding['name']} reimplements "
            f"{finding['original_file']}:{finding['original_line']} {finding['original_name']} "
            f"(similarity {float(finding['similarity']):.3f})"
        )


def _print_reports(reports: list[dupehound_report.SimilarityReport]) -> None:
    """Print deterministic evidence for each pair before verdict partitioning."""
    for report in reports:
        print(
            f"  {report.disposition}: {report.file}:{report.line} {report.name} -> "
            f"{report.original_file}:{report.original_line} {report.original_name} "
            f"(similarity {report.similarity:.3f}; "
            f"diagnostic >= {report.diagnostic_threshold:.3f}; "
            f"enforcement >= {report.enforcement_threshold:.3f}; "
            f"source {report.source_digest}; original {report.original_source_digest}; "
            f"scanner {report.scanner}; advice: {report.advice})"
        )


def verdict(parts: dict[str, list[Any]], register_size: int) -> int:
    """Print the outcome of partitioning findings against the register."""
    for note in parts["notes"]:
        print(f"dupehound gate: {note}" if note.startswith("resolved: ") else f"  {note}")
    if parts["rotted"] or parts["changed"]:
        print(
            f"dupehound gate: FAIL: {len(parts['rotted'])} register entr(ies) rotted, "
            f"{len(parts['changed'])} registered pair(s) changed since review"
        )
        return 1
    if parts["unregistered"]:
        print(f"dupehound gate: FAIL: {len(parts['unregistered'])} structural clone(s)")
        _print_findings(parts["unregistered"])
        return 1
    print(f"dupehound gate: OK: no changed function reimplementation ({register_size} reviewed-distinct pair(s))")
    return 0


def main(argv: list[str]) -> int:
    root, explicit_base = root_and_base_ref("dupehound-changed", __doc__, argv)
    base_ref = explicit_base or setting("CX_DUP_BASE_REF") or None
    paths = dupehound.selected_paths(root, dupehound.changed_paths(root, base_ref))
    if not paths:
        print("dupehound gate: OK: no changed supported-language production source")
        return 0
    print("dupehound gate: checking changed source (" + ", ".join(paths) + ")")
    executable = verified("dupehound")
    result = dupehound.run(executable, root, base_ref, threshold=DUPEHOUND_DIAGNOSTIC_THRESHOLD)
    reports = dupehound_report.reports(
        result,
        root,
        diagnostic=DUPEHOUND_DIAGNOSTIC_THRESHOLD,
        enforcement=DUPEHOUND_THRESHOLD,
        scanner=dupehound_report.SCANNER_IDENTITY,
    )
    ignored, diagnostic, blocking_reports = dupehound_report.partition_reports(reports)
    if reports:
        print(
            f"dupehound gate: report {len(reports)} pair(s); "
            f"diagnostic floor {DUPEHOUND_DIAGNOSTIC_THRESHOLD:.3f}; "
            f"enforcement {DUPEHOUND_THRESHOLD:.3f}"
        )
        _print_reports(reports)
    if ignored:
        print(f"dupehound gate: ignored {len(ignored)} pair(s) below diagnostic floor")
    if diagnostic:
        print(f"dupehound gate: {len(diagnostic)} diagnostic pair(s) require review")
    register = ledger.load_register(root)
    return verdict(ledger.partition([report.finding for report in blocking_reports], register, root), len(register))
