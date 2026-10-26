"""Bounded exact-build-scan qualification without network or secrets."""

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.architecture_explorer.activity_probe import ProbeError
from scripts.architecture_explorer.frozen_activity_probe import freeze_scope, qualify

pytestmark = pytest.mark.spec("PIPE-PAGES-R042")
NOW = "2026-10-26T04:00:00Z"
SOURCE = {
    "repository": "Knuckles-Team/pipelines",
    "commit": "a" * 40,
    "path": "scripts/architecture_explorer/registry.json",
    "fragment": "repositories + sources.scan_set(github)",
}
SCANNED = [{"slug": "pipelines", "sha": "a" * 40}, {"slug": "arbora", "sha": "b" * 40}]


def args():
    return dict(
        owner="Knuckles-Team",
        source=SOURCE,
        max_repositories=5,
        max_requests=11,
        max_graphql_cost=100,
        reserve=100,
        max_elapsed_seconds=60,
        clock=lambda: NOW,
        timer=lambda: 0,
    )


def responses(calls, *, error=None, remaining=1000):
    def request(url, query=None):
        calls.append((url, query))
        rate = {"cost": 1, "remaining": remaining, "resetAt": NOW}
        if query is None:
            name = url.split("/repos/")[1]
            if error:
                raise ProbeError("access denied; stopped")
            return {"node_id": "id:" + name, "full_name": name}
        if "repository(" not in query:
            return {"data": {"rateLimit": rate}}
        name = "Knuckles-Team/arbora" if 'name:"arbora"' in query else "Knuckles-Team/pipelines"
        return {
            "data": {
                "rateLimit": rate,
                "repository": {
                    "id": "id:" + name,
                    "nameWithOwner": name,
                    "issues": {"totalCount": 3},
                    "pullRequests": {"totalCount": 2},
                },
            }
        }

    return request


def test_exact_scope_dedupes_and_keeps_full_heads_and_per_repo_observations():
    calls = []
    got = qualify(SCANNED + [SCANNED[0]], request=responses(calls), **args())
    assert len(calls) == 5  # budget query plus identity/activity for each unique repo
    assert len(got["repositories"]) == len(got["activity"]) == 2
    assert {r["sourceCommit"] for r in got["repositories"].values()} == {"a" * 40, "b" * 40}
    assert all(
        r["openIssues"] == 3 and r["openPullRequests"] == 2 and r["observedAt"] == NOW for r in got["activity"].values()
    )
    assert "not production integration" in got["qualification"]
    assert got["budget"]["graphqlCost"] == 3
    assert got["scope"] == freeze_scope(SCANNED, owner="Knuckles-Team", source=SOURCE)


@pytest.mark.parametrize(
    "scan",
    [
        [],
        [{"slug": "pipelines"}],
        [{"slug": "pipelines", "sha": "short"}],
        [{"slug": "../private", "sha": "a" * 40}],
        SCANNED + [{"slug": "pipelines", "sha": "c" * 40}],
    ],
)
def test_bad_or_unfrozen_scope_fails_before_network(scan):
    calls = []
    with pytest.raises(ProbeError):
        qualify(scan, request=responses(calls), **args())
    assert calls == []


@pytest.mark.parametrize(
    "limit,value",
    [
        ("max_repositories", 1),
        ("max_requests", 4),
        ("max_graphql_cost", 0),
        ("reserve", True),
        ("max_elapsed_seconds", 0),
    ],
)
def test_explicit_bounds_fail_before_network(limit, value):
    config = args()
    config[limit] = value
    calls = []
    with pytest.raises(ProbeError):
        qualify(SCANNED, request=responses(calls), **config)
    assert calls == []


def test_access_denial_stops_immediately_without_partial_receipt_or_fallback():
    calls = []
    with pytest.raises(ProbeError, match="access denied"):
        qualify(SCANNED, request=responses(calls, error=True), **args())
    assert len(calls) == 2  # budget succeeded, first identity denied


def test_preflight_budget_breach_prevents_repository_queries():
    calls = []
    with pytest.raises(ProbeError, match="budget"):
        qualify(SCANNED, request=responses(calls, remaining=99), **args())
    assert len(calls) == 1


def test_cost_cap_stops_before_next_repository():
    config = args()
    config["max_graphql_cost"] = 10
    calls = []
    with pytest.raises(ProbeError, match="budget"):
        qualify(SCANNED, request=responses(calls), **config)
    assert len(calls) == 1


def test_elapsed_budget_stops_before_request():
    config = args()
    times = iter([0, 61])
    config["timer"] = lambda: next(times)
    calls = []
    with pytest.raises(ProbeError, match="budget"):
        qualify(SCANNED, request=responses(calls), **config)
    assert calls == []


def test_registry_source_is_exact_and_allowlisted():
    source = deepcopy(SOURCE)
    source["token"] = "must-not-escape"
    with pytest.raises(ProbeError):
        freeze_scope(SCANNED, owner="Knuckles-Team", source=source)


def test_configured_reserve_is_not_replaced_by_current_repo_probe_default():
    config = args()
    config["reserve"] = 10
    got = qualify(SCANNED, request=responses([], remaining=50), **config)
    assert len(got["activity"]) == 2


@pytest.mark.parametrize(
    "bad",
    [
        {},
        None,
        {"errors": [{"message": "private error"}]},
        {"data": {"rateLimit": {"cost": True, "remaining": 1000, "resetAt": NOW}}},
    ],
)
def test_bad_budget_reply_stops_without_receipt(bad):
    calls = []
    with pytest.raises(ProbeError) as error:
        qualify(SCANNED, request=lambda *args: calls.append(args) or bad, **args())
    assert len(calls) == 1
    assert "private error" not in str(error.value)


def test_source_field_types_fail_as_contract_errors():
    source = {**SOURCE, "commit": 12}
    with pytest.raises(ProbeError):
        freeze_scope(SCANNED, owner="Knuckles-Team", source=source)


def test_no_repository_call_when_preflight_only_has_reserved_points():
    calls = []
    with pytest.raises(ProbeError, match="prospective"):
        qualify(SCANNED, request=responses(calls, remaining=100), **args())
    assert len(calls) == 1


def test_unexpected_query_cost_stops_after_single_bootstrap_response():
    calls = []

    def request(*arguments):
        calls.append(arguments)
        return {"data": {"rateLimit": {"cost": 11, "remaining": 1000, "resetAt": NOW}}}

    with pytest.raises(ProbeError, match="estimate"):
        qualify(SCANNED, request=request, **args())
    assert len(calls) == 1


def test_changed_collector_query_shape_cannot_spend_budget(monkeypatch):
    calls = []

    def changed_probe(full_name, request, **kwargs):
        return request("https://api.github.com/graphql", "query { viewer { login } }")

    monkeypatch.setattr("scripts.architecture_explorer.frozen_activity_probe.probe", changed_probe)
    with pytest.raises(ProbeError, match="unreviewed query"):
        qualify(SCANNED, request=responses(calls), **args())
    assert len(calls) == 1
