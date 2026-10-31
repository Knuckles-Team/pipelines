"""connector-spec-templates: a connector's ``.specify/templates/`` equals the vended spec templates.

A connector without ``.specify/`` is reported as advisory, with the command that adds the standard. A connector
that holds ``.specify/`` fails on a missing, changed or unknown template, as ``spec-templates`` does.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.specs import templates_sync

REMEDY = "python scripts/standardize_sdd.py --root <repo> from a pipelines checkout"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-spec-templates", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    if not (root / ".specify").is_dir():
        print(f"connector-spec-templates: advisory: .specify/ is missing; run {REMEDY}")
        return 0
    found = templates_sync.mismatches(templates_sync.vended_source(), root / templates_sync.TEMPLATES)
    for line in found:
        print(f"connector-spec-templates: {line}")
    if found:
        print(f"connector-spec-templates: FAIL: run {REMEDY}")
        return 1
    print("connector-spec-templates: clean")
    return 0
