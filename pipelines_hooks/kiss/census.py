"""kiss-census: every tracked Python/Rust file under the KISS paths, enforced at zero.

Each file is checked with its own ``kiss check`` (a multi-path check reports a
false clean). Every finding fails -- there is no advisory class and no baseline.
Orphan modules are NOT covered: since kiss 0.4.11 ``kiss check`` no longer
reports ``orphan_module`` (the check moved to the coverage-linked ``kiss test``).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tools import verified
from pipelines_hooks.core.tracked import tracked_paths
from pipelines_hooks.kiss import runner
from pipelines_hooks.kiss.report import format_violation, parse_report
from pipelines_hooks.kiss.scope import in_scope, kiss_paths


def census_files(root: Path, scope: tuple[str, ...]) -> list[str]:
    """Tracked KISS-scanned files; an empty universe fails closed."""
    files = sorted(path for path in tracked_paths(root, scope) if in_scope(path, scope))
    if not files:
        raise CannotRun(f"no tracked Python or Rust source under {', '.join(scope)}")
    return files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kiss-census", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    scope = kiss_paths(root)
    runner.check_config_keys(root)
    kiss = verified("kiss")
    files = census_files(root, scope)
    findings = [format_violation(v) for path in files for v in parse_report(runner.check(kiss, root, path))]
    for line in findings:
        print(line)
    print(f"kiss census: {len(files)} file(s), {len(findings)} finding(s)")
    return 1 if findings else 0
