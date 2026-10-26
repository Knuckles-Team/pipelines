"""Qualify only an architecture build's already-frozen scan set; no discovery here."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from time import monotonic

from .activity_probe import API, ProbeError, probe
from .story_activity import timestamp

SHA = re.compile(r"[0-9a-f]{40}")
SLUG = re.compile(r"[A-Za-z0-9_.-]+")
# Conservative admission estimate for the two fixed scalar-only query shapes.
# GitHub cost formulas can change; observed higher cost fails qualification.
QUERY_COST_BOUND = 10
PREFLIGHT_QUERY = "query { rateLimit { cost remaining resetAt } }"
SOURCE_FIELDS = {"repository", "commit", "path", "fragment"}


def freeze_scope(scanned: list[dict], *, owner: str, source: dict) -> dict:
    """Accept exactly sources.scan_set's GitHub result, after source heads freeze.

    Do not substitute all organization repositories, a static registry alone, node
    labels, legacy aliases, or the public snapshot's shortened commit heads.
    Identical duplicate slugs are deduplicated; conflicting commit heads fail.
    """
    if (
        owner != "Knuckles-Team"
        or not isinstance(source, dict)
        or set(source) != SOURCE_FIELDS
        or not all(isinstance(value, str) for value in source.values())
    ):
        raise ProbeError("invalid build scan source")
    if (
        source["repository"] != owner + "/pipelines"
        or not SHA.fullmatch(source["commit"])
        or source["path"] != "scripts/architecture_explorer/registry.json"
        or source["fragment"] != "repositories + sources.scan_set(github)"
    ):
        raise ProbeError("unverified build registry/discovery provenance")
    if not isinstance(scanned, list) or not scanned:
        raise ProbeError("empty frozen scan set")
    unique = {}
    for entry in scanned:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("slug"), str)
            or not SLUG.fullmatch(entry["slug"])
            or not isinstance(entry.get("sha"), str)
            or not SHA.fullmatch(entry["sha"])
        ):
            raise ProbeError("scan set requires canonical slugs and full frozen source SHAs")
        full_name = owner + "/" + entry["slug"]
        if full_name in unique and unique[full_name] != entry["sha"]:
            raise ProbeError("conflicting frozen repository heads")
        unique[full_name] = entry["sha"]
    members = [{"fullName": name, "sourceCommit": sha} for name, sha in sorted(unique.items())]
    frozen = {"source": dict(source), "repositories": members}
    frozen["integrity"] = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    return frozen


def qualify(
    scanned: list[dict],
    *,
    owner: str,
    source: dict,
    request,
    max_repositories: int,
    max_requests: int,
    max_graphql_cost: int,
    reserve: int,
    max_elapsed_seconds: int,
    clock=lambda: datetime.now(timezone.utc).isoformat(),
    timer=monotonic,
) -> dict:
    """All-or-nothing safe receipt; fail at the first error/denial/budget breach.

    ``request`` is the reviewed existing-token transport, never an anonymous
    alternative. Caller must pass the SAME frozen scan used by the build. No
    cache or new scan is substituted. Request count is a hard local bound; GraphQL
    cost/reserve admission uses the conservative fixed-query bound, not a promise
    about concurrent token consumers or future GitHub cost changes. The elapsed
    policy is an admission/receipt deadline, not cancellation of a blocking HTTP
    call (the reviewed transport may take up to 30 seconds). REST core-rate budget
    is not measured here. No function here mutates production output.
    """
    scope = freeze_scope(scanned, owner=owner, source=source)
    limits = (max_repositories, max_requests, max_graphql_cost, reserve, max_elapsed_seconds)
    if any(type(value) is not int or value <= 0 for value in limits):
        raise ProbeError("explicit positive qualification budgets required")
    if len(scope["repositories"]) > max_repositories or 1 + 2 * len(scope["repositories"]) > max_requests:
        raise ProbeError("frozen scan exceeds request/repository budget before access")
    started = timer()
    request_count = 0
    graphql_cost = 0
    rate_receipts = []
    allowed_queries = {PREFLIGHT_QUERY}
    for member in scope["repositories"]:
        query_owner, name = member["fullName"].split("/")
        allowed_queries.add(
            (
                "query { repository(owner:%s,name:%s) { id nameWithOwner "
                "issues(states:OPEN){totalCount} pullRequests(states:OPEN){totalCount} } "
                "rateLimit { cost remaining resetAt } }"
            )
            % (json.dumps(query_owner), json.dumps(name))
        )

    def require_headroom():
        if graphql_cost + QUERY_COST_BOUND > max_graphql_cost:
            raise ProbeError("GraphQL cost budget lacks prospective query headroom")
        if rate_receipts and rate_receipts[-1]["remaining"] < reserve + QUERY_COST_BOUND:
            raise ProbeError("GraphQL reserve lacks prospective query headroom")

    def bounded(url, query=None):
        nonlocal request_count, graphql_cost
        if timer() - started >= max_elapsed_seconds or request_count >= max_requests:
            raise ProbeError("qualification time/request budget exhausted; stopped")
        if query is not None:
            if query not in allowed_queries:
                raise ProbeError("unreviewed query shape rejected before access")
            require_headroom()
        request_count += 1
        response = request(url, query) if query is not None else request(url)
        if timer() - started >= max_elapsed_seconds:
            raise ProbeError("qualification time budget exhausted; stopped")
        if query is not None:
            try:
                if response.get("errors"):
                    raise ProbeError("GraphQL error; stopped without alternate route")
                rate = response["data"]["rateLimit"]
                if any(type(rate[field]) is not int or rate[field] < 0 for field in ("cost", "remaining")):
                    raise ProbeError("malformed rate-limit evidence")
                timestamp(rate["resetAt"])
                if rate["cost"] > QUERY_COST_BOUND:
                    raise ProbeError("query cost exceeds reviewed admission estimate; stopped")
                graphql_cost += rate["cost"]
                if graphql_cost > max_graphql_cost or rate["remaining"] < reserve:
                    raise ProbeError("GraphQL budget exhausted; stopped")
                rate_receipts.append({field: rate[field] for field in ("cost", "remaining", "resetAt")})
            except (KeyError, TypeError, AttributeError, ValueError) as exc:
                if isinstance(exc, ProbeError):
                    raise
                raise ProbeError("invalid GraphQL budget evidence; stopped") from None
        return response

    # Establish the actual token budget before any per-repository access.
    bounded(API + "/graphql", PREFLIGHT_QUERY)
    repositories, observations = {}, {}
    for member in scope["repositories"]:
        require_headroom()
        observed = probe(member["fullName"], bounded, now=clock(), reserve=reserve)
        activity = observed["activity"]
        identity = activity["repositoryId"]
        if identity in repositories:
            raise ProbeError("canonical identity aliases/collisions require review")
        repositories[identity] = {
            "id": identity,
            "fullName": member["fullName"],
            "sourceCommit": member["sourceCommit"],
        }
        observations[identity] = activity
    return {
        "schemaVersion": "architecture-frozen-activity-qualification/1",
        "scope": scope,
        "qualification": "exact supplied frozen build scan only; not production integration",
        "repositories": repositories,
        "activity": observations,
        "budget": {
            "requests": request_count,
            "queryAdmissionCostBound": QUERY_COST_BOUND,
            "elapsedPolicy": "admission/receipt deadline; in-flight HTTP is not cancelled",
            "rateScope": "GraphQL only; REST requests bounded by request count",
            "graphqlCost": graphql_cost,
            "limits": {
                "repositories": max_repositories,
                "requests": max_requests,
                "graphqlCost": max_graphql_cost,
                "reserve": reserve,
                "elapsedSeconds": max_elapsed_seconds,
            },
            "rateLimitObservations": rate_receipts,
        },
    }
