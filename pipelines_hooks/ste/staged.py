"""ste-staged: staged docs and CLI strings bring no new EG-STE-Lite violation.

Diff-scoped: findings already present at HEAD are not re-reported when the
line numbers shift, so a commit fails only for the violations it adds.
New files are checked in full.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_text, has_head, repo_root, staged_paths
from pipelines_hooks.ste import scope
from pipelines_hooks.ste.code_strings import cli_findings
from pipelines_hooks.ste.report import report
from pipelines_hooks.ste.scan import Finding, check_document
from pipelines_hooks.ste.words import load_wordlist


def _index_text(root: Path, rel: str) -> str:
    text = blob_text(root, f":{rel}")
    if text is None:
        raise CannotRun(f"ste(staged): {rel} is staged but absent from the index")
    return text


def _added(before: list[Finding], after: list[Finding]) -> list[Finding]:
    prior = Counter((finding.code, finding.message) for finding in before)
    excess: dict[tuple[str, str], int] = {}
    for key, count in Counter((finding.code, finding.message) for finding in after).items():
        delta = count - prior.get(key, 0)
        if delta > 0:
            excess[key] = delta
    out: list[Finding] = []
    for finding in after:
        key = (finding.code, finding.message)
        if excess.get(key, 0) > 0:
            out.append(finding)
            excess[key] -= 1
    return out


def _added_docs(root: Path, rels: list[str], *, wordlist: object, head_present: bool) -> list[Finding]:
    out: list[Finding] = []
    for rel in rels:
        index = _index_text(root, rel)
        head = blob_text(root, f"HEAD:{rel}") if head_present else None
        out.extend(_added(check_document(head or "", wordlist, path=rel), check_document(index, wordlist, path=rel)))
    return out


def _added_code(root: Path, rels: list[str], *, wordlist: object, head_present: bool) -> list[Finding]:
    out: list[Finding] = []
    for rel in rels:
        index = _index_text(root, rel)
        head = blob_text(root, f"HEAD:{rel}") if head_present else None
        out.extend(_added(cli_findings(head or "", wordlist, path=rel), cli_findings(index, wordlist, path=rel)))
    return out


def _main(root: Path) -> int:
    cfg = scope.load_ste(root)
    wordlist = load_wordlist()
    staged = staged_paths(root)
    docs = [rel for rel in staged if scope.in_scope_doc(rel, cfg)]
    code = [rel for rel in staged if scope.in_scope_code(rel, cfg)]
    if not docs and not code:
        print("ste(staged): OK: no in-scope file staged")
        return 0
    head_present = has_head(root)
    findings = _added_docs(root, docs, wordlist=wordlist, head_present=head_present)
    findings.extend(_added_code(root, code, wordlist=wordlist, head_present=head_present))
    return report("ste(staged)", findings)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ste-staged", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return _main(repo_root(parser.parse_args(argv).root))
