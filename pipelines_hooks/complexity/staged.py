"""complexity-staged: no NEW or WORSENED function over cyclomatic 10 / cognitive 15.

Compares the INDEX (``git show :path``) against HEAD, never the working tree,
so an unstaged edit can neither hide a violation nor invent one. Every staged
file in a cccc-supported language is measured -- no path is excluded -- and
the Rust exhaustive-dispatch terms of acceptance
(:mod:`pipelines_hooks.rust.dispatch`) are applied to both sides.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from pipelines_hooks.complexity import MAX_COGNITIVE, MAX_CYCLOMATIC, cccc
from pipelines_hooks.complexity.judge import Finding, Graded, file_summary, grade, judge, rust_source
from pipelines_hooks.core.gitenv import blob_text, repo_root, staged_paths
from pipelines_hooks.core.tools import verified

ADVICE = """
Split the function into named parts, or replace the branching with a dict
dispatch table. Flattening nesting into a longer chain trades one metric for
the other and is not a fix; recurse until every function you created is under
BOTH caps. A cyclomatic-only finding on a flat Rust `match` was checked against
the terms of acceptance first: if it was reported, one of the four conditions
does not hold (most often a catch-all arm). Do NOT raise a threshold and do NOT
add a suppression comment -- an in-line suppression is a one-line baseline.
"""


def _measure(executable: str, text: str, *, suffix: str, scratch: Path) -> dict[str, list[Graded]]:
    handle = tempfile.NamedTemporaryFile("w", suffix=suffix, dir=scratch, delete=False, encoding="utf-8")
    with handle:
        handle.write(text)
    path = Path(handle.name)
    document = cccc.run(executable, [path.name], cwd=scratch)
    rows = [row for _, row in cccc.file_rows(document)]
    return grade(rows, rust_source(path))


def _render(rel: str, finding: Finding) -> str:
    if finding.kind == "WORSE":
        return (
            f"  WORSE  cyc {finding.before[0]}->{finding.after[0]}  "
            f"cog {finding.before[1]}->{finding.after[1]}   {finding.name}@{rel}"
        )
    flags = [f"cyc {finding.after[0]}"] * (finding.after[0] > MAX_CYCLOMATIC)
    flags += [f"COG {finding.after[1]}"] * (finding.after[1] > MAX_COGNITIVE)
    return f"  NEW    over cap ({', '.join(flags)})   {finding.name}@{rel}"


def check_file(root: Path, rel: str, *, executable: str, scratch: Path) -> list[Finding]:
    """Findings for one staged file."""
    staged = blob_text(root, f":{rel}")
    if staged is None:
        return []
    suffix = Path(rel).suffix
    after = _measure(executable, staged, suffix=suffix, scratch=scratch)
    summary = file_summary(rel, after)
    if summary:
        print(summary)
    head = blob_text(root, f"HEAD:{rel}")
    before = _measure(executable, head, suffix=suffix, scratch=scratch) if head is not None else {}
    findings = judge(before, after)
    for finding in findings:
        print(_render(rel, finding))
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="complexity-staged", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    files = [p for p in staged_paths(root) if Path(p).suffix.lower() in cccc.SUPPORTED_SUFFIXES]
    if not files:
        print("complexity(staged): OK: no staged file in a cccc-supported language")
        return 0
    executable = verified("cccc")
    print(f"complexity(staged): {len(files)} file(s), caps cyclomatic {MAX_CYCLOMATIC} / cognitive {MAX_COGNITIVE}")
    with tempfile.TemporaryDirectory(prefix="cx-staged-") as raw:
        findings = [f for rel in files for f in check_file(root, rel, executable=executable, scratch=Path(raw))]
    if not findings:
        print("\ncomplexity(staged): OK: nothing new over a cap, nothing regressed")
        return 0
    new = sum(f.kind == "NEW" for f in findings)
    print(f"\ncomplexity(staged): FAIL: {new} new over a cap, {len(findings) - new} made worse")
    print(ADVICE)
    return 1
