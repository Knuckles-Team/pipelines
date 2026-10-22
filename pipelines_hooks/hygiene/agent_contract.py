"""agent-contract: the repository gives a cold agent one-command setup and the standard AGENTS.md section.

Warn level (exit 0): a missing ``scripts/bootstrap.sh``, a missing
``AGENTS.md``, or an ``AGENTS.md`` without the marked standard section is
reported but does not fail. ``--strict`` makes the findings blocking, for the
day the fleet has converged. Reads the tracked set only, never the filesystem.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths

START = "<!-- agent-contract:start -->"
END = "<!-- agent-contract:end -->"
ORG_AGENTS = "https://github.com/Knuckles-Team/.github/blob/main/AGENTS.md"
#: Labels the standard section carries, in the order the standard states them.
LABELS = ("**Owner boundary:**", "**Setup:**", "**Gates:**", "**Commits:**")


def inspect(root: Path, paths: list[str]) -> list[str]:
    """Every finding for one repository (an empty list means conformant)."""
    findings: list[str] = []
    if "scripts/bootstrap.sh" not in paths:
        findings.append("scripts/bootstrap.sh is not tracked")
    if "AGENTS.md" not in paths:
        findings.append("AGENTS.md is not tracked")
        return findings
    text = (root / "AGENTS.md").read_text(encoding="utf-8", errors="replace")
    start, end = text.find(START), text.find(END)
    if start < 0 or end < start:
        findings.append(f"AGENTS.md lacks the {START} ... {END} section")
        return findings
    block = text[start:end]
    findings.extend(f"agent-contract section lacks {label}" for label in LABELS if label not in block)
    if ORG_AGENTS not in block:
        findings.append(f"agent-contract section does not link {ORG_AGENTS}")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent-contract", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--strict", action="store_true", help="fail on findings instead of warning")
    arguments = parser.parse_args(argv)
    root = repo_root(arguments.root)
    findings = inspect(root, tracked_paths(root))
    if not findings:
        print("agent-contract: conformant (scripts/bootstrap.sh and the standard AGENTS.md section)")
        return 0
    level = "FAIL" if arguments.strict else "WARN"
    print(f"{level}: agent-contract (reference/ci-standard.md, Agent contract):")
    for finding in findings:
        print(f"  {finding}")
    return 1 if arguments.strict else 0
