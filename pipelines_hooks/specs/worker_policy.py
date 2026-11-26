"""ingest-worker-policy: the worker admission policy has one owner, the durable kernel rows.

``specs/ingest-worker`` must not restate the worker's numbers. The policy values (the ``0.36``
fraction, the ``3 GiB`` figure and the phrase ``reserved floor``) are owned by
``MEDULLA-DURABLE-KERNEL-R074`` to ``R077``. A line of that spec that holds one of them passes only
when the same line cites one of those rows by ID. Fenced code is skipped. A repository without
``specs/ingest-worker`` has nothing to check and passes.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.specs.artifacts import unfenced

SPEC_DIR = Path("specs") / "ingest-worker"
POLICY_RE = re.compile(r"(?<![\w.])0\.36(?![\w])|\b3 GiB\b|reserved floor", re.I)
CITATION_RE = re.compile(r"\bMEDULLA-DURABLE-KERNEL-R07[4-7](?:\.\d+)*\b")


def scan_text(rel: str, text: str) -> list[str]:
    """One finding per unfenced line that restates a policy value without citing its owner row."""
    return [
        f"{rel}:{number}: restates the worker policy ({match.group(0)!r}) without citing MEDULLA-DURABLE-KERNEL-R074 to R077"
        for number, line in unfenced(text)
        if (match := POLICY_RE.search(line)) and not CITATION_RE.search(line)
    ]


def scan(root: Path) -> list[str]:
    base = root / SPEC_DIR
    if not base.is_dir():
        return []
    findings: list[str] = []
    for path in sorted(base.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise CannotRun(f"cannot read {path}: {exc}") from exc
        findings.extend(scan_text(path.relative_to(root).as_posix(), text))
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ingest-worker-policy", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    findings = scan(root)
    for finding in findings:
        print(f"  - {finding}")
    if findings:
        print("ingest-worker-policy FAILED.")
        return 1
    print("ingest-worker-policy: OK: no duplicate worker policy")
    return 0
