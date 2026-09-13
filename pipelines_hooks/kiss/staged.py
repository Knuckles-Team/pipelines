"""kiss-staged: KISS findings the staged diff is responsible for, and no others.

Reads only the staged index (materialized with ``git checkout-index``) and
narrows each report against a report on the HEAD blob of the same file
(:mod:`pipelines_hooks.kiss.report`). Untouched pre-existing debt in a changed
file does not fail the commit; it stays visible in kiss-census.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root, staged_paths
from pipelines_hooks.core.tools import verified
from pipelines_hooks.kiss import runner
from pipelines_hooks.kiss.report import Violation, attributable, format_violation, parse_report
from pipelines_hooks.kiss.scope import in_scope, kiss_paths
from pipelines_hooks.kiss.spans import spans_for


def _file_findings(kiss: str, trees: tuple[Path, Path | None], path: str) -> list[Violation]:
    staged_tree, head_tree = trees
    report = runner.check(kiss, staged_tree, path)
    if not parse_report(report):
        return []
    staged = ((staged_tree / path).read_text(encoding="utf-8"), report)
    head_file = None if head_tree is None else head_tree / path
    head = None
    if head_file is not None and head_file.is_file():
        head = (head_file.read_text(encoding="utf-8"), runner.check(kiss, head_tree, path))
    findings = attributable(staged, head, spans_for(path))
    untouched = len(parse_report(report)) - len(findings)
    print(f"kiss(staged): {len(findings)} attributable violation(s) in {path} ({untouched} untouched, not counted)")
    return findings


def staged_findings(root: Path, scope: tuple[str, ...], paths: list[str]) -> list[Violation]:
    """Attributable findings over the materialized staged index and HEAD tree."""
    kiss = verified("kiss")
    with tempfile.TemporaryDirectory(prefix="kiss-staged-") as raw:
        staged_tree = runner.materialize_index(root, Path(raw) / "index")
        runner.check_config(staged_tree)
        runner.reject_symlinks(staged_tree, scope)
        head_tree = runner.materialize_head(root, Path(raw) / "head")
        return [f for path in paths for f in _file_findings(kiss, (staged_tree, head_tree), path)]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kiss-staged", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    scope = kiss_paths(root)
    paths = [path for path in staged_paths(root) if in_scope(path, scope)]
    if not paths:
        print(f"kiss(staged): OK: no staged Python or Rust source under {', '.join(scope)}")
        return 0
    findings = staged_findings(root, scope, paths)
    for violation in findings:
        print(format_violation(violation))
    print(f"kiss(staged): {len(findings)} attributable violation(s) across {len(paths)} changed file(s)")
    return 1 if findings else 0
