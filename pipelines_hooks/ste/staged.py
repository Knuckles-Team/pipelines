"""ste-staged: staged docs and CLI strings bring no new EG-STE-Lite violation.

Local runs compare the staged index with HEAD; CI compares its commit range.
Diff-scoped: findings already present at the base are not re-reported when the
line numbers shift, so a commit fails only for the violations it adds.
New files are checked in full.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.args import root_and_base_ref
from pipelines_hooks.core.comparison import comparison
from pipelines_hooks.core.gitenv import blob_text
from pipelines_hooks.ste import scope
from pipelines_hooks.ste.code_strings import cli_findings
from pipelines_hooks.ste.report import report
from pipelines_hooks.ste.scan import Finding, check_document
from pipelines_hooks.ste.words import load_wordlist


def _after_text(root: Path, rel: str, ref: str) -> str:
    text = blob_text(root, f"{ref}:{rel}")
    if text is None:
        raise CannotRun(f"ste(staged): {rel} is changed but absent from the comparison tree")
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


def _added_paths(
    root: Path,
    rels: list[str],
    *,
    wordlist: object,
    before_ref: str | None,
    after_ref: str,
    check: Callable[[str, object, str], list[Finding]],
) -> list[Finding]:
    out: list[Finding] = []
    for rel in rels:
        index = _after_text(root, rel, after_ref)
        head = blob_text(root, f"{before_ref}:{rel}") if before_ref else None
        out.extend(_added(check(head or "", wordlist, path=rel), check(index, wordlist, path=rel)))
    return out


def _main(root: Path, base_ref: str | None) -> int:
    cfg = scope.load_ste(root)
    wordlist = load_wordlist()
    staged, before, after = comparison(root, base_ref)
    docs = [rel for rel in staged if scope.in_scope_doc(rel, cfg)]
    code = [rel for rel in staged if scope.in_scope_code(rel, cfg)]
    if not docs and not code:
        print("ste(staged): OK: no in-scope file changed" if after else "ste(staged): OK: no in-scope file staged")
        return 0
    findings = _added_paths(root, docs, wordlist=wordlist, before_ref=before, after_ref=after, check=check_document)
    findings.extend(_added_paths(root, code, wordlist=wordlist, before_ref=before, after_ref=after, check=cli_findings))
    return report("ste(staged)", findings)


def main(argv: list[str]) -> int:
    root, base_ref = root_and_base_ref("ste-staged", __doc__, argv)
    return _main(root, base_ref)
