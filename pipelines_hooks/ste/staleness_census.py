"""ste-staleness-census: every tracked in-scope doc line is claim-valid.

Zero findings is the closing criterion for a repository's stale-claim
program. The census tolerates an empty universe (exit 0): a repository
with no in-scope docs has nothing to verify.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.ste import scope
from pipelines_hooks.ste.report import report
from pipelines_hooks.ste.scan import Finding
from pipelines_hooks.ste.staleness import check_lines


def _numbered(root: Path, rel: str) -> list[tuple[int, str]]:
    try:
        lines = (root / rel).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"ste-staleness(census): cannot read {rel}: {exc}") from exc
    return list(enumerate(lines, 1))


def _main(root: Path) -> int:
    cfg = scope.load_ste(root)
    if not cfg.staleness:
        print("ste-staleness(census): OK: no staleness patterns configured")
        return 0
    findings: list[Finding] = []
    for rel in scope.doc_files(root, cfg):
        findings.extend(check_lines(rel, _numbered(root, rel), cfg.staleness))
    return report("ste-staleness(census)", findings)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ste-staleness-census", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return _main(repo_root(parser.parse_args(argv).root))
