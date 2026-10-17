"""Read-only preflight binding a release tag to the frozen build source."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("GitHub API redirect refused")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def commit_sha(value: object) -> str:
    require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None, "invalid release commit identity"
    )
    return value


def frozen_source(environment: dict) -> str:
    source = commit_sha(environment.get("SOURCE_COMMIT"))
    require(
        source == environment.get("EXPECTED_COMMIT") == environment.get("LATEST_COMMIT"),
        "release metadata differs from frozen workflow source",
    )
    head = subprocess.check_output(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        text=True,
        timeout=10,
    ).strip()
    require(head == source, "HEAD differs from frozen build source")
    return source


def api_get(path: str, environment: dict, *, missing: bool = False) -> dict | None:
    base = environment.get("RELEASE_API_URL", "")
    parsed = urlsplit(base)
    require(
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not (parsed.username or parsed.password or parsed.query or parsed.fragment),
        "invalid GitHub API origin",
    )
    token = environment.get("RELEASE_TOKEN", "")
    require(bool(token), "missing GitHub read token")
    request = Request(
        base.rstrip("/") + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
    except HTTPError as error:
        if missing and error.code == 404:
            return None
        raise ValueError(f"GitHub metadata unavailable (HTTP {error.code})") from error
    require(len(raw) <= 1024 * 1024, "GitHub metadata exceeds size limit")
    document = json.loads(raw)
    require(isinstance(document, dict), "invalid GitHub metadata object")
    return document


def release_tag(environment: dict) -> str:
    version = environment.get("BUILD_VERSION", "")
    require(re.fullmatch(r"[0-9][A-Za-z0-9._+-]*", version) is not None, "invalid release version")
    return "refs/tags/v" + version


def tag_commit(document: dict, prefix: str, environment: dict) -> str:
    for _ in range(8):
        target = document.get("object")
        require(isinstance(target, dict), "invalid tag target")
        sha = commit_sha(target.get("sha"))
        kind = target.get("type")
        if kind == "commit":
            return sha
        require(kind == "tag", "release tag does not resolve to a commit")
        document = api_get(prefix + "/git/tags/" + sha, environment)
        require(document.get("sha") == sha, "annotated tag identity mismatch")
    raise ValueError("release tag nesting exceeds limit")


def verify(environment: dict) -> str:
    source = frozen_source(environment)
    repository = environment.get("RELEASE_REPOSITORY", "")
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is not None, "invalid release repository")
    prefix = "/repos/" + repository
    # Prove repository access first: its 404 must never count as an absent tag.
    metadata = api_get(prefix, environment)
    require(metadata.get("full_name", "").casefold() == repository.casefold(), "GitHub repository identity mismatch")
    tag = release_tag(environment)
    document = api_get(prefix + "/git/ref/" + tag.removeprefix("refs/"), environment, missing=True)
    if document is not None:
        require(document.get("ref") == tag, "GitHub returned a different tag")
        require(
            tag_commit(document, prefix, environment) == source,
            "existing release tag conflicts with frozen build source",
        )
    return source


def main() -> int:
    try:
        source = verify(dict(os.environ))
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"commit={source}\n")
    except (ValueError, OSError, KeyError, URLError, subprocess.SubprocessError) as error:
        print(f"Release source blocked: {error}", file=sys.stderr)
        return 1
    print(f"Release source verified: {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
