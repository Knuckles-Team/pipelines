"""Validate the public README and current-state AGENTS contract.

The gate is intentionally offline.  Badge URLs and Pages links are checked
for canonical syntax and repository containment; reachability is a CI/Pages
responsibility, not a non-deterministic pre-commit side effect.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.docs.public_surface_config import (
    PublicSurfaceConfig,
    load_public_surface_config,
)
from pipelines_hooks.docs.public_surface_constants import LINK_RE
from pipelines_hooks.docs.public_surface_links import link_destination, local_link_findings
from pipelines_hooks.docs.public_surface_text import (
    badge_findings,
    forbidden_findings,
    h1_count,
    line_findings,
    required_headings,
)


def _read(root: Path, name: str) -> str | None:
    path = root / name
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"cannot read {name}: {exc}") from exc


def _pages_finding(readme: str, config: PublicSurfaceConfig) -> list[str]:
    links = {
        link_destination(match.group(1)).rstrip("/") or "/"
        for match in LINK_RE.finditer(readme)
    }
    if config.pages_url not in links:
        return [f"README.md must link to the configured Pages URL {config.pages_url!r}"]
    return []


def _readme_findings(root: Path, readme: str, config: PublicSurfaceConfig) -> list[str]:
    findings = line_findings("README.md", readme, agents=False)
    count = h1_count(readme)
    if count != 1:
        findings.append(f"README.md must contain exactly one H1 (found {count})")
    missing = required_headings(readme, agents=False)
    if missing:
        findings.append("README.md is missing required heading(s): " + ", ".join(missing))
    findings.extend(badge_findings(readme, config))
    findings.extend(_pages_finding(readme, config))
    findings.extend(local_link_findings(root, readme))
    findings.extend(forbidden_findings("README.md", readme))
    return findings


def _agents_findings(root: Path, agents: str) -> list[str]:
    findings = line_findings("AGENTS.md", agents, agents=True)
    count = h1_count(agents)
    if count != 1:
        findings.append(f"AGENTS.md must contain exactly one H1 (found {count})")
    missing = required_headings(agents, agents=True)
    if missing:
        findings.append("AGENTS.md is missing required durable heading(s): " + ", ".join(missing))
    findings.extend(local_link_findings(root, agents))
    findings.extend(forbidden_findings("AGENTS.md", agents))
    return findings


def validate(root: Path) -> list[str]:
    """Return all public-surface findings for ``root``."""
    config = load_public_surface_config(root)
    readme = _read(root, "README.md")
    agents = _read(root, "AGENTS.md")
    findings: list[str] = []
    if readme is None:
        findings.append("README.md is required")
    else:
        findings.extend(_readme_findings(root, readme, config))
    if agents is None:
        findings.append("AGENTS.md is required")
    else:
        findings.extend(_agents_findings(root, agents))
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="public-surface", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    findings = validate(repo_root(parser.parse_args(argv).root))
    if not findings:
        print("public surface: clean (README.md and AGENTS.md)")
        return 0
    print("FAIL: public README/AGENTS surface contract.")
    for finding in findings:
        print(f"  - {finding}")
    return 1
