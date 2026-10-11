"""Drill-down URL forms and link parity: ecosystem -> repository -> spec."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_graph.model import REPOS

SITE = "https://knuckles-team.github.io"
KINDS = {"repository": "", "spec": "#spec-", "requirement": "#req-"}


def ecosystem_components():
    """Core repository slugs, exactly the shared list; no second list is defined."""
    return list(REPOS)


def anchor_for(kind, ident, repo=None):
    """Return the stable URL (repo given) or in-page fragment for a drill-down level."""
    if kind not in KINDS:
        raise ValueError(f"unknown drill-down kind: {kind}")
    fragment = KINDS[kind] + (str(ident) if kind != "repository" else "")
    if repo is None:
        return fragment
    return f"{SITE}/{repo}/spec-delivery/{fragment}"


def check_drilldown_links(html, components=None):
    """Return unresolved drill-down targets in generated HTML (pure, no network)."""
    problems = []
    for repo in ecosystem_components() if components is None else components:
        if anchor_for("repository", repo, repo) not in html:
            problems.append(f"missing component link: {repo}")
    ids = set(re.findall(r'\bid="((?:spec|req)-[^"]+)"', html))
    for target in sorted(set(re.findall(r'href="#((?:spec|req)-[^"]+)"', html))):
        if target not in ids:
            problems.append(f"unresolved anchor: #{target}")
    return problems


def drilldown_exit(html, components=None):
    """Exit status for the parity check: 1 when any link target is unresolved."""
    return 1 if check_drilldown_links(html, components) else 0
