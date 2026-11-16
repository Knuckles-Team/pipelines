"""Tag a green version bump on main so the same run publishes it (PIPE-RELEASE-R018.3).

``python3 -I release_autotag.py --root . --repository OWNER/NAME --sha SHA`` runs in the
connector pipeline after the full main suite passed on ``SHA``. It reads ``[project].version``
and creates the annotated tag ``v<version>`` on ``SHA`` through the API, unless the version is
not ``MAJOR.MINOR.PATCH``, the tag exists, the package index serves the version, or the version
is not newer than every released tag and index version. It writes ``tag=<tag or empty>`` to
``$GITHUB_OUTPUT``. Every skip is a notice and exit 0; an unreadable API or index exits 1.
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
from pathlib import Path

API = "https://api.github.com"
PYPI = "https://pypi.org/pypi"
RELEASE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class AlreadyExists(Exception):
    """The tag ref was created by someone else between the check and the write."""


def _key(version: str) -> tuple[int, int, int] | None:
    match = RELEASE.match(version)
    return None if match is None else (int(match[1]), int(match[2]), int(match[3]))


def newest_release(tags: set[str], published: set[str]) -> str | None:
    """The newest MAJOR.MINOR.PATCH among the v* tags and the index versions."""
    versions = {tag.removeprefix("v") for tag in tags if tag.startswith("v")} | published
    keyed = [(key, version) for version in versions if (key := _key(version)) is not None]
    return max(keyed)[1] if keyed else None


def decide(version: str, tags: set[str], published: set[str]) -> tuple[str | None, str]:
    """(tag to create or None, reason)."""
    if _key(version) is None:
        return None, f"version {version!r} is not MAJOR.MINOR.PATCH; nothing to tag"
    tag = f"v{version}"
    if tag in tags:
        return None, f"tag {tag} already exists"
    if version in published:
        return None, f"the package index already serves {version}"
    newest = newest_release(tags, published)
    if newest is not None and _key(version) <= _key(newest):
        return None, f"main's version {version} is not newer than the released {newest}; bump main past it"
    return tag, f"{version} is new and green; tagging {tag}"


def _request(url: str, token: str | None = None, data: dict | None = None) -> bytes:
    headers = {"User-Agent": "release-autotag", "Accept": "application/vnd.github+json"}
    if token and url.startswith(API):
        headers["Authorization"] = f"Bearer {token}"
    body = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method="GET" if data is None else "POST")
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - https only
        return response.read()


def remote_tags(repository: str, token: str, request=_request) -> set[str]:
    try:
        refs = json.loads(request(f"{API}/repos/{repository}/git/matching-refs/tags/v", token))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return set()
        raise
    return {ref["ref"].removeprefix("refs/tags/") for ref in refs}


def index_versions(name: str, request=_request) -> set[str]:
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    try:
        return set(json.loads(request(f"{PYPI}/{normalized}/json"))["releases"])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return set()
        raise


def create_tag(repository: str, tag: str, sha: str, token: str, request=_request) -> None:
    """Annotated tag object, then its ref; a ref that already exists raises AlreadyExists."""
    obj = json.loads(
        request(
            f"{API}/repos/{repository}/git/tags",
            token,
            {"tag": tag, "message": f"Release {tag}", "object": sha, "type": "commit"},
        )
    )
    try:
        request(f"{API}/repos/{repository}/git/refs", token, {"ref": f"refs/tags/{tag}", "sha": obj["sha"]})
    except urllib.error.HTTPError as error:
        if error.code == 422:
            raise AlreadyExists(tag) from error
        raise


def run(root: Path, repository: str, sha: str, token: str, request=_request) -> str:
    """The created tag, or '' with the reason printed as a notice."""
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    if "name" not in project or not isinstance(project.get("version"), str):
        print("::notice::no static [project] name and version; nothing to tag")
        return ""
    version = project["version"]
    tag, reason = decide(version, remote_tags(repository, token, request), index_versions(project["name"], request))
    if tag is None:
        print(f"::notice::{reason}")
        return ""
    try:
        create_tag(repository, tag, sha, token, request)
    except AlreadyExists:
        print(f"::notice::tag {tag} was created concurrently; nothing to publish here")
        return ""
    print(f"::notice::tagged {tag} on {sha}; this run publishes it")
    return tag


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        print("::error::--sha must be a full commit SHA")
        return 1
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN is required to read and create tags")
        return 1
    tag = run(args.root, args.repository, args.sha, token)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"tag={tag}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
