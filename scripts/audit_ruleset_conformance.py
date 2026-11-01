"""Audit that every registered repository's default branch requires exactly `CI required`.

Read-only. It lists the repositories of the pages-explorer registry, skips archived ones and the
explicit EXCLUDE entries, and reads the effective branch rules and repository settings through
the GitHub API. It prints one line per drift and exits 1 when any exists. It never changes a
repository: the owner applies `scripts/apply_repo_ci_settings.sh` after reviewing the list.

Usage: GH_TOKEN=<read token> python scripts/audit_ruleset_conformance.py [--repo owner/name ...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "scripts" / "architecture_explorer" / "registry.json"
REQUIRED = "CI required"
# Repositories audited although the pages registry does not list them (front-door hub).
EXTRA = (".github",)
# Repository -> reason it is not audited yet. An entry is removed when its reason ends.
EXCLUDE = {"medulla": "excluded until its 3.0.0 landing merges"}

Api = Callable[[str], object]


def registry_repos(path: Path = REGISTRY) -> tuple[str, list[str]]:
    """Return the owner and the registered repository names plus the extras."""
    data = json.loads(path.read_text(encoding="utf-8"))
    names = [entry["slug"] for entry in data["repositories"]]
    return data["owner"], sorted({*names, *EXTRA})


def github_api(token: str) -> Api:
    """Return a GET function for the GitHub REST API."""

    def get(path: str) -> object:
        req = urllib.request.Request(
            f"https://api.github.com/{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "ruleset-audit",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https host
            return json.loads(resp.read())

    return get


def required_checks(rules: list[dict]) -> set[str]:
    """Union of the contexts of every required-status-checks rule that applies to the branch."""
    found: set[str] = set()
    for rule in rules:
        if rule.get("type") == "required_status_checks":
            found.update(c["context"] for c in rule["parameters"]["required_status_checks"])
    return found


def audit_repo(api: Api, owner: str, name: str) -> list[str]:
    """Drift findings of one repository; empty when it conforms or is archived."""
    info = api(f"repos/{owner}/{name}")
    if info["archived"]:
        return []
    findings: list[str] = []
    rules = api(f"repos/{owner}/{name}/rules/branches/{info['default_branch']}")
    checks = required_checks(rules)
    if checks != {REQUIRED}:
        shown = ", ".join(sorted(checks)) or "no required check"
        findings.append(f"{name}: main requires [{shown}], expected exactly [{REQUIRED}]")
    if not info.get("allow_auto_merge"):
        findings.append(f"{name}: allow_auto_merge is off")
    return findings


def audit(api: Api, owner: str, names: list[str], exclude: dict[str, str] = EXCLUDE) -> list[str]:
    """Drift findings across the repositories, skipping the excluded ones."""
    findings: list[str] = []
    for name in names:
        if name in exclude:
            continue
        try:
            findings.extend(audit_repo(api, owner, name))
        except urllib.error.HTTPError as exc:
            findings.append(f"{name}: cannot read settings (HTTP {exc.code})")
    return findings


def main(argv: list[str] | None = None, api: Api | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=[], help="audit only these repository names")
    args = parser.parse_args(argv)
    owner, names = registry_repos()
    names = args.repo or names
    if api is None:
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            print("ruleset audit: CANNOT RUN: GH_TOKEN is not set", file=sys.stderr)
            return 2
        api = github_api(token)
    for name, reason in EXCLUDE.items():
        print(f"excluded: {name} ({reason})")
    findings = audit(api, owner, names)
    for line in findings:
        print(f"DRIFT {line}")
    print(f"ruleset audit: {len(findings)} drift finding(s) across {len(names)} repositories")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
