"""Offline qualification contracts; production API calls only in the reviewed workflow."""

from pathlib import Path
import sys
import urllib.error

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.architecture_explorer.activity_probe import API, NoRedirect, ProbeError, probe, transport

pytestmark = pytest.mark.spec("PIPE-PAGES-R042")
NOW = "2026-10-26T04:00:00Z"
NAME = "Knuckles-Team/pipelines"


def test_probe_uses_identity_then_separate_graphql_counts():
    calls = []

    def request(url, query=None):
        calls.append((url, query))
        if query is None:
            return {"node_id": "R_1", "full_name": NAME}
        return {
            "data": {
                "repository": {
                    "id": "R_1",
                    "nameWithOwner": NAME,
                    "issues": {"totalCount": 2},
                    "pullRequests": {"totalCount": 3},
                },
                "rateLimit": {"cost": 1, "remaining": 1000, "resetAt": NOW},
            }
        }

    output = probe(NAME, request, now=NOW)
    assert [call[0] for call in calls] == [API + "/repos/" + NAME, API + "/graphql"]
    assert output["activity"]["openIssues"] == 2
    assert output["activity"]["openPullRequests"] == 3
    assert output["scope"] == "current repository only; not fleet qualification"


@pytest.mark.parametrize(
    "response", [None, {}, {"full_name": NAME, "node_id": ""}, {"full_name": "other/repo", "node_id": "R_1"}]
)
def test_identity_failure_stops_before_graphql(response):
    calls = []
    with pytest.raises(ProbeError):
        probe(NAME, lambda *args: calls.append(args) or response, now=NOW)
    assert len(calls) == 1


def test_graphql_error_is_terminal_and_safe():
    calls = []

    def request(url, query=None):
        calls.append(url)
        return (
            {"node_id": "R_1", "full_name": NAME}
            if query is None
            else {"errors": [{"message": "credential detail must not escape"}]}
        )

    with pytest.raises(ProbeError, match="no cache, retry or fallback") as error:
        probe(NAME, request, now=NOW)
    assert "credential" not in str(error.value)
    assert len(calls) == 2


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_http_failure_has_one_attempt_no_fallback_and_no_raw_diagnostics(monkeypatch, status):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            raise urllib.error.HTTPError(request.full_url, status, "secret raw detail", {}, None)

    monkeypatch.setattr("urllib.request.build_opener", lambda handler: Opener())
    with pytest.raises(ProbeError) as error:
        transport("synthetic-test-value")(API + "/repos/" + NAME)
    assert len(calls) == 1
    assert "secret" not in str(error.value)


def test_no_credentials_or_redirect_alternatives():
    with pytest.raises(ProbeError):
        transport("")
    with pytest.raises(ProbeError):
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.example")
    with pytest.raises(ProbeError):
        transport("synthetic-test-value")("https://elsewhere.example")


def test_workflow_is_separate_read_only_and_has_no_fallback():
    workflow = (Path(__file__).parents[1] / ".github/workflows/architecture_activity_probe.yml").read_text()
    assert "contents: read" in workflow and ": write" not in workflow
    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow
    assert "pull_request_target" not in workflow and "secrets." not in workflow
    assert "persist-credentials: false" in workflow
    assert "continue-on-error" not in workflow
    assert "head.repo.full_name == github.repository" in workflow
    assert "activity_probe" in workflow
