"""mermaid: validate every Mermaid block embedded in Markdown.

Given file arguments (pre-commit passes staged ``.md`` files) it checks those;
without arguments it checks every tracked ``.md`` file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths
from pipelines_hooks.hygiene.mermaid_rules import BlockLine, Finding, validate_block


def check_file(path: Path) -> list[Finding]:
    """Findings for every Mermaid block in one Markdown file."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        return [{"line": 0, "message": f"Error reading file: {exc}"}]
    findings: list[Finding] = []
    block: list[BlockLine] | None = None
    start = 0
    for number, raw in enumerate(lines, 1):
        clean = raw.strip()
        if block is None and clean.startswith("```mermaid"):
            block, start = [], number
        elif block is not None and clean.startswith("```"):
            findings.extend(validate_block(start, block))
            block = None
        elif block is not None:
            block.append((number, raw))
    if block is not None:
        findings.append({"line": start, "message": "Unclosed Mermaid code block (missing closing ```)."})
    return findings


def markdown_files(root: Path, files: list[str]) -> list[str]:
    """The given Markdown files, or every tracked one."""
    selected = [name for name in files if name.endswith(".md")]
    return selected or [path for path in tracked_paths(root) if path.endswith(".md")]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mermaid", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    names = markdown_files(root, args.files)
    report = {name: check_file(root / name) for name in names if (root / name).is_file()}
    lines = [f"{name}:{f['line']}: {f['message']}" for name, findings in report.items() for f in findings]
    print("\n".join(lines))
    if lines:
        print(f"MERMAID DIAGRAM SYNTAX VERIFICATION FAILED: {len(lines)} error(s)")
        return 1
    print(f"mermaid: OK: {len(names)} Markdown file(s) checked")
    return 0
