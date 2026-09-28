"""public-surface: the README (and AGENTS.md when present) point at things that exist.

The gate checks only what breaks for a reader: a missing README, a relative
link or image whose target is absent or outside the repository, a link with a
non-web URL scheme, and a README that never says how to install or start the
project. Wording, length and section layout are review matters, not gates.
The gate is offline: web links are not fetched.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.docs.public_surface_links import local_link_findings
from pipelines_hooks.docs.public_surface_quickstart import findings as quick_start_findings


def _read(root: Path, name: str) -> str | None:
    path = root / name
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"cannot read {name}: {exc}") from exc


def validate(root: Path) -> list[str]:
    """Return all public-surface findings for ``root``."""
    readme = _read(root, "README.md")
    if readme is None:
        return ["README.md is required"]
    findings = quick_start_findings(readme) + local_link_findings(root, readme, name="README.md")
    agents = _read(root, "AGENTS.md")
    if agents is not None:
        findings += local_link_findings(root, agents, name="AGENTS.md")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="public-surface", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    findings = validate(repo_root(parser.parse_args(argv).root))
    if not findings:
        print("public surface: clean")
        return 0
    print("FAIL: public README/AGENTS surface.")
    for finding in findings:
        print(f"  - {finding}")
    return 1
