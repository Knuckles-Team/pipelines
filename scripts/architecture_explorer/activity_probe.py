"""Opt-in existing-token read-only qualification; no retries, cache or fallback."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .story_activity import ActivityError, collect

API = "https://api.github.com"


class ProbeError(ValueError):
    """Safe diagnostic category without raw response or credential data."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeError("redirect refused; no alternate access route")


def transport(token: str):
    if not token:
        raise ProbeError("existing GITHUB_TOKEN is required")
    opener = urllib.request.build_opener(NoRedirect())

    def request(url: str, query: str | None = None) -> dict:
        if not re.fullmatch(r"https://api\.github\.com/(graphql|repos/[^/\s]+/[^/\s]+)", url):
            raise ProbeError("unexpected endpoint")
        body = json.dumps({"query": query}).encode() if query is not None else None
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": "Bearer " + token,
                "User-Agent": "architecture-activity-qualification",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        try:
            with opener.open(req, timeout=30) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ProbeError("response exceeds probe limit")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            category = "access denied" if exc.code in {401, 403, 404} else "HTTP failure"
            raise ProbeError(category + "; stopped without retry or fallback") from None
        except (OSError, ValueError) as exc:
            if isinstance(exc, ProbeError):
                raise
            raise ProbeError("transport or JSON failure; stopped") from None

    return request


def probe(full_name: str, request, *, now: str, reserve: int = 100) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
        raise ProbeError("invalid current repository identity")
    metadata = request(API + "/repos/" + full_name)
    if (
        not isinstance(metadata, dict)
        or metadata.get("full_name") != full_name
        or not isinstance(metadata.get("node_id"), str)
        or not metadata["node_id"]
    ):
        raise ProbeError("canonical repository identity could not be verified")
    repo = {"id": metadata["node_id"], "fullName": full_name}
    try:
        records = collect(
            [repo], request=lambda query: request(API + "/graphql", query), now=now, max_age_seconds=60, reserve=reserve
        )
    except ActivityError:
        raise ProbeError("GraphQL activity verification failed; no cache, retry or fallback") from None
    return {
        "scope": "current repository only; not fleet qualification",
        "repository": full_name,
        "activity": records[repo["id"]],
    }


def main() -> int:
    try:
        result = probe(
            os.environ.get("GITHUB_REPOSITORY", ""),
            transport(os.environ.get("GITHUB_TOKEN", "")),
            now=datetime.now(timezone.utc).isoformat(),
        )
    except ProbeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
