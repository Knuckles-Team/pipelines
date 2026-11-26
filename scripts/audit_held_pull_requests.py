"""Audit that no held pull request has an armed merge request (PIPE-GATES-R062).

Read-only. For every registered, non-archived repository it lists the open pull requests and reports
each one that carries the ``hold`` label and has auto-merge armed. It prints one line per finding
(repository, number, label) and exits 1 when any exists. It only issues GET requests; the owner
disarms the merge request after reading the list. The label is documented in the organization
front-door repository.

Usage: GH_TOKEN=<read token> python scripts/audit_held_pull_requests.py [--repo owner/name ...]
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_ruleset_conformance import Api, github_api, registry_repos  # noqa: E402

HOLD_LABEL = "hold"
PAGE = 100


def open_pull_requests(api: Api, owner: str, name: str) -> list[dict]:
    """Every open pull request of one repository, read page by page."""
    found: list[dict] = []
    page = 1
    while True:
        batch = api(f"repos/{owner}/{name}/pulls?state=open&per_page={PAGE}&page={page}")
        found.extend(batch)
        if len(batch) < PAGE:
            return found
        page += 1


def armed_held(api: Api, owner: str, name: str) -> list[str]:
    """One finding per open pull request that carries the hold label and has an armed merge."""
    return [
        f"{name}#{pr['number']}: carries the {HOLD_LABEL!r} label and has an armed merge request"
        for pr in open_pull_requests(api, owner, name)
        if pr.get("auto_merge") and any(label.get("name") == HOLD_LABEL for label in pr.get("labels", []))
    ]


def main(argv: list[str] | None = None, api: Api | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=[], help="audit only these repository names")
    args = parser.parse_args(argv)
    owner, names = registry_repos()
    names = args.repo or names
    if api is None:
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            print("hold audit: CANNOT RUN: GH_TOKEN is not set", file=sys.stderr)
            return 2
        api = github_api(token)
    findings: list[str] = []
    for name in names:
        try:
            findings.extend(armed_held(api, owner, name))
        except urllib.error.HTTPError as exc:
            findings.append(f"{name}: cannot read pull requests (HTTP {exc.code})")
    for line in findings:
        print(f"FINDING {line}")
    print(f"hold audit: {len(findings)} finding(s) across {len(names)} repositories")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
