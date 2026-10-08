"""ste-census: every tracked in-scope doc and CLI string carries no violation.

Retro-verification gate: after a repository has been rewritten, this must
report zero before the rewrite is accepted. The gate fails closed (exit 2)
when no in-scope doc is tracked at all -- a repository that cannot have
in-scope docs has a scope configuration error, not a clean state.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.ste import scope
from pipelines_hooks.ste.code_strings import cli_findings
from pipelines_hooks.ste.report import report
from pipelines_hooks.ste.scan import Finding, check_document
from pipelines_hooks.ste.words import load_wordlist


def _read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"ste(census): cannot read {rel}: {exc}") from exc


def _main(root: Path) -> int:
    cfg = scope.load_ste(root)
    wordlist = load_wordlist()
    docs = scope.doc_files(root, cfg)
    if not docs:
        raise CannotRun("ste(census): no tracked in-scope document; declare ste.paths or drop the gate")
    findings: list[Finding] = []
    for rel in docs:
        findings.extend(check_document(_read(root, rel), wordlist, path=rel))
    for rel in scope.code_files(root, cfg):
        findings.extend(cli_findings(_read(root, rel), wordlist, path=rel))
    return report("ste(census)", findings)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ste-census", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return _main(repo_root(parser.parse_args(argv).root))
