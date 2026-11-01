"""workflow-step-honesty: a test or check step in a workflow exits with the tool's real status.

Fails on a ``run:`` command that is a test or check tool and whose failure is masked by
``; true``, ``|| true``, ``|| :``, ``|| exit 0`` or a trailing ``set +e``. Scans the workflow
files and the workflow templates. A cleanup command (``rm``, ``cp``, ``git fetch``) may
still use ``|| true``: only a test or check command is a finding.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths

PATHSPECS = (".github/workflows/*.yml", ".github/workflows/*.yaml", "templates/workflows/*.yml")
CHECK_TOOL = re.compile(
    r"\b(pytest|nextest|unittest|tox|nox|mypy|pyright|ruff|clippy|pre-commit|pipelines-hook"
    r"|cargo\s+(?:\S+\s+)*(?:test|nextest|clippy|check|deny|audit|fmt)|go\s+test|npm\s+(?:run\s+)?test|pnpm\s+test"
    r"|yarn\s+test|make\s+(?:test|check)|pip-audit|jscpd|dupehound)\b"
)
MASK = re.compile(r"(?:;\s*true|\|\|\s*true|\|\|\s*:|\|\|\s*exit\s+0)\s*(?:#.*)?$")


def _logical_lines(script: str) -> list[str]:
    """Join backslash continuations so a mask on a continued line is seen with its command."""
    joined, current = [], ""
    for raw in script.splitlines():
        current += raw.rstrip("\\").strip() + " "
        if not raw.rstrip().endswith("\\"):
            joined.append(current.strip())
            current = ""
    return joined + ([current.strip()] if current.strip() else [])


def _steps(document: object) -> list[dict]:
    jobs = document.get("jobs", {}) if isinstance(document, dict) else {}
    return [s for job in jobs.values() if isinstance(job, dict) for s in job.get("steps", []) if isinstance(s, dict)]


def scan_text(rel: str, text: str) -> list[str]:
    findings: list[str] = []
    for step in _steps(yaml.safe_load(text)):
        script = step.get("run")
        if not isinstance(script, str):
            continue
        findings.extend(
            f"{rel}: step {step.get('name', '?')!r}: failure masked after a test or check: {line}"
            for line in _logical_lines(script)
            if CHECK_TOOL.search(line) and MASK.search(line)
        )
    return findings


def scan(root: Path) -> list[str]:
    findings = []
    for rel in tracked_paths(root, PATHSPECS):
        findings.extend(scan_text(rel, (root / rel).read_text(encoding="utf-8")))
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="workflow-step-honesty", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    findings = scan(root)
    for finding in sorted(findings):
        print(f"  - {finding}")
    if findings:
        print("workflow-step-honesty FAILED.")
        return 1
    print("workflow-step-honesty: OK: no masked test or check step")
    return 0
