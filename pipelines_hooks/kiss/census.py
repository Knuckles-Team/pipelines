"""kiss-census: every tracked Python/Rust file under the KISS paths, enforced at zero.

Each file is checked with its own ``kiss check`` (a multi-path check reports a
false clean). When ``.kiss/kiss.toml`` enables ``orphan_module_enabled``, each
KISS path is ALSO checked as one directory: orphan detection needs the whole
package's import graph, and a single-file check never reports an orphan. Every
finding fails -- there is no advisory class and no baseline.
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


def orphan_findings(kiss: str, root: Path, files: list[str]) -> list[str]:
    """``orphan_module`` findings from one whole-directory check per path and language."""
    if not runner.orphan_rule_enabled(root):
        print("kiss census: orphan_module_enabled is off in .kiss/kiss.toml")
        return []
    directories = sorted({(str(Path(path).parts[0]), runner.LANGUAGES[Path(path).suffix]) for path in files})
    return [
        format_violation(violation)
        for directory, language in directories
        for violation in parse_report(runner.check(kiss, root, directory, language=language))
        if violation["rule"] == "orphan_module"
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kiss-census", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    scope = kiss_paths(root)
    runner.check_config(root)
    kiss = verified("kiss")
    files = census_files(root, scope)
    findings = [format_violation(v) for path in files for v in parse_report(runner.check(kiss, root, path))]
    orphans = orphan_findings(kiss, root, files)
    for line in [*findings, *orphans]:
        print(line)
    print(f"kiss census: {len(files)} file(s), {len(findings)} finding(s), {len(orphans)} orphan module(s)")
    return 1 if findings or orphans else 0
