"""Build-only repository activity; injected transport, no credentials in artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Callable

QUERY_VERSION = "github-open-activity/1"


class ActivityError(ValueError):
    """A required repository observation cannot be trusted."""


def timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError
        return result
    except (ValueError, AttributeError) as exc:
        raise ActivityError("timezone-aware timestamp required") from exc


def digest(record: dict) -> str:
    """Bind immutable observation fields, not latest refresh-attempt metadata."""
    keys = (
        "repositoryId",
        "fullName",
        "observedAt",
        "lastVerifiedAt",
        "openPullRequests",
        "openIssues",
        "queryVersion",
    )
    return hashlib.sha256(json.dumps({k: record[k] for k in keys}, sort_keys=True).encode()).hexdigest()


def validate(record: dict, repo: dict, now: str, max_age_seconds: int) -> None:
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise ActivityError("explicit positive maximum cache age required")
    try:
        if record["repositoryId"] != repo["id"] or record["fullName"] != repo["fullName"]:
            raise ActivityError("cache repository identity changed")
        if record["queryVersion"] != QUERY_VERSION or record["integrity"] != digest(record):
            raise ActivityError("unverified observation")
        if any(type(record[k]) is not int or record[k] < 0 for k in ("openPullRequests", "openIssues")):
            raise ActivityError("invalid activity counts")
        observed, verified, current = (
            timestamp(record["observedAt"]),
            timestamp(record["lastVerifiedAt"]),
            timestamp(now),
        )
        if observed != verified or not 0 <= (current - verified).total_seconds() <= max_age_seconds:
            raise ActivityError("expired or future observation")
        if record["freshness"] not in {"fresh", "stale"} or record["refreshOutcome"] not in {"ok", "failed"}:
            raise ActivityError("invalid refresh state")
        if (record["freshness"] == "fresh") != (record["refreshOutcome"] == "ok"):
            raise ActivityError("inconsistent refresh state")
        attempted = timestamp(record["attemptedAt"])
        if not verified <= attempted <= current:
            raise ActivityError("invalid attempted timestamp")
        if record["refreshOutcome"] == "ok" and (record.get("failureCategory") is not None or attempted != verified):
            raise ActivityError("inconsistent successful observation")
        if record["refreshOutcome"] == "failed" and record.get("failureCategory") not in {
            "transport",
            "response",
            "budget",
        }:
            raise ActivityError("missing failure category")
    except (KeyError, TypeError) as exc:
        raise ActivityError("incomplete observation") from exc


def collect(
    repositories: list[dict],
    *,
    request: Callable[[str], dict],
    now: str,
    max_age_seconds: int,
    cache: dict | None = None,
    reserve: int = 100,
) -> dict:
    """One bounded query per repository; no retries, credential discovery or REST fallback.

    The caller owns an authorized transport and budget window. Stop additional API
    calls on any failed/partial/budget response. Fallback is per-repository validated
    last-known-good, with original timestamps. Returned cache is all-or-nothing.
    """
    timestamp(now)
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise ActivityError("explicit positive maximum cache age required")
    if not repositories or any(
        not isinstance(r.get("id"), str) or not r["id"] or not re.fullmatch(r"[^/\s]+/[^/\s]+", r.get("fullName", ""))
        for r in repositories
    ):
        raise ActivityError("invalid repository identity")
    if len({r["fullName"] for r in repositories}) != len(repositories):
        raise ActivityError("duplicate repository name")
    if type(reserve) is not int or reserve < 0:
        raise ActivityError("invalid rate reserve")
    if len({r["id"] for r in repositories}) != len(repositories):
        raise ActivityError("duplicate repository")
    result, failure = {}, None
    for repo in repositories:
        try:
            if failure:
                raise ActivityError(failure)
            owner, name = repo["fullName"].split("/")
            query = (
                "query { repository(owner:%s,name:%s) { id nameWithOwner "
                "issues(states:OPEN){totalCount} pullRequests(states:OPEN){totalCount} } "
                "rateLimit { cost remaining resetAt } }"
            ) % (json.dumps(owner), json.dumps(name))
            try:
                response = request(query)
            except (OSError, TimeoutError) as exc:
                raise ActivityError("transport") from exc
            try:
                if response.get("errors"):
                    raise ActivityError("response")
                data = response["data"]
                value, rate = data["repository"], data["rateLimit"]
                if value["id"] != repo["id"] or value["nameWithOwner"] != repo["fullName"]:
                    raise ActivityError("response")
                if any(type(rate[k]) is not int or rate[k] < 0 for k in ("cost", "remaining")):
                    raise ActivityError("response")
                timestamp(rate["resetAt"])
                if rate["remaining"] < reserve:
                    raise ActivityError("budget")
                record = dict(
                    repositoryId=repo["id"],
                    fullName=repo["fullName"],
                    observedAt=now,
                    lastVerifiedAt=now,
                    attemptedAt=now,
                    freshness="fresh",
                    refreshOutcome="ok",
                    failureCategory=None,
                    openIssues=value["issues"]["totalCount"],
                    openPullRequests=value["pullRequests"]["totalCount"],
                    queryVersion=QUERY_VERSION,
                )
                record["integrity"] = digest(record)
                validate(record, repo, now, max_age_seconds)
            except (KeyError, TypeError, AttributeError, ActivityError) as exc:
                raise ActivityError("budget" if str(exc) == "budget" else "response") from exc
        except ActivityError as exc:
            failure = str(exc)
            record = dict((cache or {}).get(repo["id"], {}))
            validate(record, repo, now, max_age_seconds)
            record.update(attemptedAt=now, freshness="stale", refreshOutcome="failed", failureCategory=failure)
        result[repo["id"]] = record
    return result
