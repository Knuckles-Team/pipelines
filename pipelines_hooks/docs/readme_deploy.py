"""readme-deploy-block: the README carries one well-formed generated deployment block.

The block sits between ``<!-- BEGIN GENERATED: additional-deployment-options -->``
and its ``END`` marker. The gate fails when the README is missing, has no block,
has an unbalanced, repeated or reversed marker, an empty block, or a block that
names a mutable ``:latest`` image. The work-tree root is resolved with Git, so
the check runs the same from a linked worktree; a root it cannot resolve is
``CannotRun`` (exit status 2), never a skipped pass (PIPE-GATES-R076).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root

BEGIN = "<!-- BEGIN GENERATED: additional-deployment-options -->"
END = "<!-- END GENERATED: additional-deployment-options -->"
_MUTABLE_IMAGE = re.compile(r":latest\b", re.IGNORECASE)


def block_findings(readme: str) -> list[str]:
    """Findings for the deployment block of one README text."""
    begins, ends = readme.count(BEGIN), readme.count(END)
    if begins == 0 and ends == 0:
        return ["README.md has no generated deployment block"]
    if begins != 1 or ends != 1:
        return [f"README.md must hold exactly one deployment block (found {begins} begin and {ends} end markers)"]
    start, stop = readme.index(BEGIN), readme.index(END)
    if stop < start:
        return ["README.md deployment block ends before it begins"]
    body = readme[start + len(BEGIN) : stop]
    findings = [] if body.strip() else ["README.md deployment block is empty"]
    if _MUTABLE_IMAGE.search(body):
        findings.append("README.md deployment block names a mutable :latest image; pin a digest")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="readme-deploy-block", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    path = root / "README.md"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print("readme-deploy-block: FAIL: README.md is required")
        return 1
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"cannot read {path}: {exc}") from exc
    findings = block_findings(text)
    for finding in findings:
        print(f"  {finding}")
    if findings:
        print(f"readme-deploy-block: FAIL: {len(findings)} finding(s)")
        return 1
    print("readme-deploy-block: OK: one well-formed deployment block")
    return 0
