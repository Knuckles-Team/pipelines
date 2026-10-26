"""Pure producer/cache tests: no credential, API or layout dependency."""

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.architecture_explorer.story_activity import ActivityError, collect
from scripts.architecture_explorer.story_contract import ContractError, export_atomic, produce

pytestmark = pytest.mark.spec("PIPE-PAGES-R042")
NOW = "2026-10-26T04:00:00Z"
REPO = {"id": "R_1", "fullName": "Knuckles-Team/pipelines", "url": "https://github.com/Knuckles-Team/pipelines"}
P = {"repository": REPO["fullName"], "commit": "a" * 40, "path": "specs/demo/requirements.md", "fragment": "ROW-1"}


def mapped(keys, state=None):
    return {
        "state": state or ("complete" if keys else "none_declared"),
        "keys": keys,
        "provenance": P,
        **({"reason": "Reviewed fixture declaration"} if not keys else {}),
    }


def response():
    return {
        "data": {
            "repository": {
                "id": "R_1",
                "nameWithOwner": REPO["fullName"],
                "issues": {"totalCount": 7},
                "pullRequests": {"totalCount": 3},
            },
            "rateLimit": {"cost": 1, "remaining": 4000, "resetAt": "2026-10-26T05:00:00Z"},
        }
    }


def fixture():
    rows = [
        {
            "key": "R_1:" + rid,
            "id": rid,
            "repositoryId": "R_1",
            "title": rid,
            "family": "demo",
            "status": state,
            "functional": True,
            "rollup": False,
            "provenance": P,
            "placement": P,
            "dependencies": mapped([]),
        }
        for rid, state in [("ROW-1", "SPECIFIED"), ("ROW-2", "VERIFIED")]
    ]
    nodes = [
        {
            "id": nid,
            "parentId": parent,
            "kind": kind,
            "label": {"text": "Unicode λ", "provenance": P},
            "purpose": {"text": "Test purpose", "provenance": P},
            "ownership": mapped(["R_1"]),
            "specs": mapped(keys),
            "relationships": mapped([]),
        }
        for nid, parent, kind, keys in [
            ("root", None, "aggregate", []),
            ("leaf", "root", "internal_leaf", [r["key"] for r in rows]),
            ("duplicate-placement", "root", "internal_leaf", [rows[0]["key"]]),
        ]
    ]
    return dict(
        nodes=nodes,
        rows=rows,
        repositories=[REPO],
        activity=collect([REPO], request=lambda q: response(), now=NOW, max_age_seconds=3600),
        built_at=NOW,
        max_age_seconds=3600,
    )


def test_exact_counts_dedupe_completed_na_and_scored_zero():
    output = produce(**fixture())
    root = output["nodes"]["root"]
    assert root["statusCounts"] == {"SPECIFIED": 1, "VERIFIED": 1, "LANDED": 0, "RETIRED": 0}
    assert root["repositoryActivity"] == {"openIssues": 7, "openPullRequests": 3}
    assert output["rows"]["R_1:ROW-1"]["priority"]["value"] == 0
    assert output["rows"]["R_1:ROW-2"]["priority"]["state"] == "not_applicable"
    assert "value" not in output["rows"]["R_1:ROW-2"]["priority"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda f: f["rows"][0].update(status="UNKNOWN"),
        lambda f: f["rows"][0].update(dependencies=mapped(["R_1:MISSING"])),
        lambda f: f["rows"].append(deepcopy(f["rows"][0])),
        lambda f: f["nodes"][1].pop("specs"),
        lambda f: f["nodes"][1].update(specs={"state": "complete", "keys": [], "provenance": P}),
        lambda f: f["nodes"][1].update(relationships=mapped(["MISSING"])),
        lambda f: f["nodes"][1].update(ownership=mapped(["unknown"])),
        lambda f: f["nodes"][1]["label"].update(provenance={**P, "commit": "a" * 10}),
        lambda f: f["nodes"][0].update(parentId="leaf"),
    ],
)
def test_invalid_sources_cannot_replace_output(tmp_path, mutation):
    inputs = fixture()
    mutation(inputs)
    destination = tmp_path / "story.json"
    destination.write_text("last known artifact")
    with pytest.raises((ContractError, ActivityError)):
        export_atomic(destination, **inputs)
    assert destination.read_text() == "last known artifact"
    assert list(tmp_path.iterdir()) == [destination]


def test_dependency_direction_readiness_and_priority():
    inputs = fixture()
    inputs["rows"][1].update(status="SPECIFIED", dependencies=mapped(["R_1:ROW-1"]))
    output = produce(**inputs)
    assert output["rows"]["R_1:ROW-1"]["priority"]["value"] == 2
    assert output["rows"]["R_1:ROW-2"]["readiness"] == "blocked"
    assert output["nodes"]["root"]["dependencyEdges"][0]["target"] == "R_1:ROW-1"


def test_successful_export_is_detached_and_utf8(tmp_path):
    inputs = fixture()
    result = export_atomic(tmp_path / "story.json", **inputs)
    inputs["nodes"][0]["label"]["text"] = "Changed"
    assert result["nodes"]["root"]["label"]["text"] == "Unicode λ"
    assert "λ" in (tmp_path / "story.json").read_text()


def test_failed_refresh_keeps_timestamp_and_counts_without_poisoning_cache():
    cache = fixture()["activity"]
    before = deepcopy(cache)
    output = collect(
        [REPO],
        request=lambda q: {"errors": [{"message": "forbidden"}]},
        now="2026-10-26T04:10:00Z",
        max_age_seconds=3600,
        cache=cache,
    )
    assert output["R_1"]["lastVerifiedAt"] == NOW
    assert output["R_1"]["observedAt"] == NOW
    assert output["R_1"]["freshness"] == "stale"
    assert output["R_1"]["refreshOutcome"] == "failed"
    assert output["R_1"]["openIssues"] == 7
    assert cache == before


@pytest.mark.parametrize("bad", [None, {}, {"data": {"repository": None}}, {"errors": ["denied"]}])
def test_missing_cache_never_invents_zero(bad):
    with pytest.raises(ActivityError):
        collect([REPO], request=lambda q: bad, now=NOW, max_age_seconds=3600)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["R_1"].update(openIssues=0),
        lambda c: c["R_1"].update(repositoryId="changed"),
        lambda c: c["R_1"].update(queryVersion="old"),
    ],
)
def test_unverified_cache_is_rejected(mutate):
    cache = fixture()["activity"]
    mutate(cache)
    with pytest.raises(ActivityError):
        collect([REPO], request=lambda q: {}, now=NOW, max_age_seconds=3600, cache=cache)


def test_expired_cache_and_partial_count_fail():
    cache = fixture()["activity"]
    with pytest.raises(ActivityError):
        collect([REPO], request=lambda q: {}, now="2026-10-26T06:00:00Z", max_age_seconds=3600, cache=cache)
    data = response()
    del data["data"]["repository"]["pullRequests"]
    with pytest.raises(ActivityError):
        collect([REPO], request=lambda q: data, now=NOW, max_age_seconds=3600)


def test_stop_network_after_failure_or_budget_exhaustion():
    calls = []
    data = response()
    data["data"]["rateLimit"]["remaining"] = 0
    with pytest.raises(ActivityError):
        collect([REPO], request=lambda q: calls.append(q) or data, now=NOW, max_age_seconds=3600)
    assert len(calls) == 1


@pytest.mark.parametrize("count", [True, -1, 1.5, "3", None])
def test_noninteger_activity_never_verified(count):
    data = response()
    data["data"]["repository"]["issues"]["totalCount"] = count
    with pytest.raises(ActivityError):
        collect([REPO], request=lambda q: data, now=NOW, max_age_seconds=3600)


def test_explicit_empty_spec_mapping_requires_provenance_and_reason():
    inputs = fixture()
    inputs["nodes"][1]["specs"] = {"state": "not_applicable", "keys": []}
    with pytest.raises(ContractError):
        produce(**inputs)


def test_ambiguous_bare_ids_fail_even_when_canonical_keys_differ():
    inputs = fixture()
    row = deepcopy(inputs["rows"][0])
    row["key"] = "R_2:ROW-1"
    inputs["rows"].append(row)
    with pytest.raises(ContractError, match="ambiguous bare"):
        produce(**inputs)


def test_transport_failure_uses_verified_cache_only():
    def fail(query):
        raise TimeoutError("do not serialize transport detail or credential")

    result = collect([REPO], request=fail, now=NOW, max_age_seconds=3600, cache=fixture()["activity"])
    assert result["R_1"]["failureCategory"] == "transport"
    assert "credential" not in str(result)


def test_query_has_separate_open_counts_and_identity():
    queries = []
    collect([REPO], request=lambda q: queries.append(q) or response(), now=NOW, max_age_seconds=3600)
    assert "issues(states:OPEN){totalCount}" in queries[0]
    assert "pullRequests(states:OPEN){totalCount}" in queries[0]
    assert "rateLimit { cost remaining resetAt }" in queries[0]


@pytest.mark.parametrize("max_age", [0, -1, True, None])
def test_invalid_cache_policy_fails_before_network(max_age):
    calls = []
    with pytest.raises(ActivityError):
        collect([REPO], request=lambda q: calls.append(q), now=NOW, max_age_seconds=max_age)
    assert calls == []


def test_failure_stops_remaining_requests_and_returns_only_verified_cache():
    other = {"id": "R_2", "fullName": "Knuckles-Team/arbora"}
    data = response()
    data["data"]["repository"].update(id="R_2", nameWithOwner=other["fullName"])
    cache = fixture()["activity"] | collect([other], request=lambda q: data, now=NOW, max_age_seconds=3600)
    calls = []
    output = collect(
        [REPO, other],
        request=lambda q: calls.append(q) or {"errors": ["denied"]},
        now=NOW,
        max_age_seconds=3600,
        cache=cache,
    )
    assert len(calls) == 1
    assert all(record["freshness"] == "stale" for record in output.values())


@pytest.mark.parametrize("pollution", ["credential detail", {"token": "must not escape"}])
def test_success_metadata_pollution_is_rejected(pollution):
    inputs = fixture()
    inputs["activity"]["R_1"]["failureCategory"] = pollution
    with pytest.raises(ActivityError):
        produce(**inputs)


@pytest.mark.parametrize("reason", [True, {"not": "a reason"}, "   "])
def test_review_reason_must_be_nonempty_text(reason):
    inputs = fixture()
    inputs["nodes"][0]["specs"]["reason"] = reason
    with pytest.raises(ContractError):
        produce(**inputs)


@pytest.mark.parametrize("identity", ["", "   ", 3, " root"])
def test_node_ids_are_nonempty_canonical_strings(identity):
    inputs = fixture()
    inputs["nodes"][0]["id"] = identity
    with pytest.raises(ContractError):
        produce(**inputs)


def test_family_summaries_use_repository_identity():
    assert produce(**fixture())["nodes"]["root"]["families"] == {"R_1:demo": 2}


def test_failed_atomic_replace_preserves_old_output_and_cleans_staging(tmp_path, monkeypatch):
    from scripts.architecture_explorer import story_contract

    destination = tmp_path / "story.json"
    destination.write_text("previous verified output")

    def fail(source, target):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(story_contract.os, "replace", fail)
    with pytest.raises(OSError):
        export_atomic(destination, **fixture())
    assert destination.read_text() == "previous verified output"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("status", ["LANDED", "VERIFIED", "RETIRED"])
def test_priority_na_describes_formula_exclusion_not_delivery_qualification(status):
    inputs = fixture()
    inputs["rows"][1]["status"] = status
    row = produce(**inputs)["rows"]["R_1:ROW-2"]
    assert row["status"] == status
    assert row["priority"]["reason"] == "delivery state is excluded by the scoring formula (no longer open)"
    assert "value" not in row["priority"]
