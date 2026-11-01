"""Report a package whose version on main was never published (PIPE-RELEASE-R027).

``python scripts/release_drift.py`` reads the organization registry the architecture explorer
uses. For each registered repository it compares the ``[project].version`` in ``pyproject.toml``
on the default branch with the releases on the package index. A repository drifts when that
version is unpublished and the head commit of the default branch is older than the grace
period. The report lists each drift; the exit code is 1. The script never tags, publishes or
edits anything.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent / "architecture_explorer" / "registry.json"
GRACE = timedelta(hours=24)
# Repositories that are skipped on purpose, each with the reason.
EXCLUDED = {
    "medulla": "excluded until its 3.0.0 landing merges",
}


def normalize(name: str) -> str:
    """The index's normalized project name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _get(url: str, token: str | None = None, raw: bool = False) -> bytes | None:
    """GET a URL; None for a 404."""
    headers = {"User-Agent": "release-drift"}
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    if raw:
        headers["Accept"] = "application/vnd.github.raw"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:  # noqa: S310 - https only
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def main_state(slug: str, owner: str, token: str | None, get=_get) -> tuple[str, str, datetime] | None:
    """(project name, version, head commit time) of the default branch; None without a static version."""
    api = f"https://api.github.com/repos/{owner}/{slug}"
    meta = get(api, token)
    text = get(f"{api}/contents/pyproject.toml", token, True)
    if meta is None or text is None:
        return None
    branch = json.loads(meta)["default_branch"]
    project = tomllib.loads(text.decode()).get("project", {})
    if "name" not in project or "version" not in project:
        return None
    head = json.loads(get(f"{api}/commits/{branch}", token) or b"{}")
    when = datetime.fromisoformat(head["commit"]["committer"]["date"].replace("Z", "+00:00"))
    return project["name"], project["version"], when


def published(name: str, get=_get) -> set[str] | None:
    """Versions on the index; None when the project is not there."""
    body = get(f"https://pypi.org/pypi/{normalize(name)}/json")
    return None if body is None else set(json.loads(body)["releases"])


def is_archived(slug: str, owner: str, token: str | None, get=_get) -> bool:
    meta = get(f"https://api.github.com/repos/{owner}/{slug}", token)
    return meta is None or bool(json.loads(meta).get("archived"))


def audit(registry: dict, now: datetime, token: str | None = None, get=_get, grace: timedelta = GRACE) -> list[str]:
    """One line per drifting repository."""
    owner, findings = registry["owner"], []
    for entry in registry["repositories"]:
        slug = entry["slug"]
        if slug in EXCLUDED or is_archived(slug, owner, token, get):
            continue
        state = main_state(slug, owner, token, get)
        if state is None:
            continue
        name, version, when = state
        versions = published(name, get)
        if versions is not None and version in versions:
            continue
        if now - when <= grace:
            continue
        seen = "not on the index" if versions is None else "unpublished"
        findings.append(f"{slug}: main has {name} {version} ({seen}); head is {when:%Y-%m-%d %H:%M}Z")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    args = parser.parse_args(argv)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    findings = audit(registry, datetime.now(UTC), os.environ.get("GITHUB_TOKEN"))
    for slug, reason in EXCLUDED.items():
        print(f"excluded {slug}: {reason}")
    for line in findings:
        print(f"DRIFT {line}")
    print(f"release drift: {len(findings)} repositories with an unpublished version on main")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
