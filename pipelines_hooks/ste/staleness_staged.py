"""ste-staleness-staged: staged doc lines add no stale ownership claim.

Only the lines the commit adds are checked (the staged diff, zero context):
reordering old text is not a violation. Patterns come from the bundled gate
defaults plus the consumer's own staleness table.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.gitenv import git_text, repo_root, staged_paths
from pipelines_hooks.ste import scope
from pipelines_hooks.ste.report import report
from pipelines_hooks.ste.scan import Finding
from pipelines_hooks.ste.staleness import check_lines

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _added_lines(root: Path, rel: str) -> list[tuple[int, str]]:
    """(line number, text) pairs for every added line in the staged diff."""
    raw = git_text(root, ("diff", "--cached", "--unified=0", "--", rel), preserve_index=True)
    lines: list[tuple[int, str]] = []
    number = 0
    for text in raw.splitlines():
        head = _HUNK.match(text)
        if head:
            number = int(head.group(1))
        elif text.startswith("+") and not text.startswith("+++"):
            lines.append((number, text[1:]))
            number += 1
    return lines


def _main(root: Path) -> int:
    cfg = scope.load_ste(root)
    if not cfg.staleness:
        print("ste-staleness(staged): OK: no staleness patterns configured")
        return 0
    docs = [rel for rel in staged_paths(root) if scope.in_scope_doc(rel, cfg)]
    if not docs:
        print("ste-staleness(staged): OK: no in-scope doc staged")
        return 0
    findings: list[Finding] = []
    for rel in docs:
        findings.extend(check_lines(rel, _added_lines(root, rel), cfg.staleness))
    return report("ste-staleness(staged)", findings)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ste-staleness-staged", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return _main(repo_root(parser.parse_args(argv).root))
