"""Red nightlies become issues (PIPE-GATES-R103), with a fake GitHub API."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import nightly_health  # noqa: E402

NOW = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)
LOG = (
    "﻿2026-11-16T13:37:39.0587821Z #14 resolving\n"
    "2026-11-16T13:42:15.1Z ##[error]Because there is no version of demo==0.3.9\n"
    "2026-11-16T13:42:15.2Z ##[error]Process completed with exit code 1.\n"
)


def _run(run_id: int, workflow: int, name: str, conclusion: str, status: str = "completed") -> dict:
    return {
        "id": run_id,
        "workflow_id": workflow,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "html_url": f"https://github.com/Org/demo/actions/runs/{run_id}",
        "head_sha": "f" * 40,
        "head_branch": "main",
        "updated_at": "2026-11-16T13:55:00Z",
    }


class FakeApi(nightly_health.Api):
    """One organization held in memory; records every write."""

    def __init__(self, repos: list[dict], runs: dict[str, list[dict]], issues: dict[str, list[dict]] | None = None):
        super().__init__("tok")
        self.repos, self.runs = repos, runs
        self.issues = issues or {}
        self.labels: dict[str, set[str]] = {}
        self.writes: list[tuple[str, str, dict]] = []

    def call(self, method: str, path: str, data: dict | None = None, raw: bool = False) -> bytes | None:
        if method != "GET":
            self.writes.append((method, path, data))
            return json.dumps(self._write(method, path, data)).encode()
        if path.startswith("/orgs/Org/repos"):
            return json.dumps(self.repos if "page=1" in path else []).encode()
        repo = "/".join(path.split("/")[2:4])
        if path.endswith("/actions/workflows?per_page=100"):
            return json.dumps(
                {
                    "workflows": [
                        {"id": 1, "name": "Connector", "state": "active"},
                        {"id": 2, "name": "Old", "state": "disabled_manually"},
                    ]
                }
            ).encode()
        if "/actions/runs?event=schedule" in path:
            return json.dumps({"workflow_runs": self.runs.get(repo, []) if "page=1" in path else []}).encode()
        if "/jobs?filter=latest" in path:
            jobs = [
                {"id": 9, "name": "pipeline / publish-docker", "conclusion": "failure"},
                {"id": 8, "name": "pipeline / resolve", "conclusion": "success"},
            ]
            return json.dumps({"jobs": jobs if "page=1" in path else []}).encode()
        if path.endswith("/actions/jobs/9/logs"):
            return LOG.encode()
        if "/labels/nightly-red" in path:
            return (
                json.dumps({"name": "nightly-red"}).encode() if "nightly-red" in self.labels.get(repo, set()) else None
            )
        if "/issues?" in path:
            found = [i for i in self.issues.get(repo, []) if i["state"] == "open"]
            return json.dumps(found if "page=1" in path else []).encode()
        raise AssertionError(f"unexpected GET {path}")

    def _write(self, method: str, path: str, data: dict) -> dict:
        repo = "/".join(path.split("/")[2:4])
        if path.endswith("/labels"):
            self.labels.setdefault(repo, set()).add(data["name"])
            return data
        if method == "POST" and path.endswith("/issues"):
            issue = {"number": 7, "state": "open", "html_url": f"https://github.com/{repo}/issues/7", **data}
            self.issues.setdefault(repo, []).append(issue)
            return issue
        if method == "PATCH":
            number = int(path.rsplit("/", 1)[1])
            issue = next(i for i in self.issues[repo] if i["number"] == number)
            issue.update(data)
            return issue
        return {}


REPO = {"full_name": "Org/demo", "archived": False, "has_issues": True}


@pytest.mark.spec("PIPE-GATES-R103")
def test_a_red_nightly_opens_one_issue_with_the_run_jobs_and_errors() -> None:
    # The newest completed run counts; an in-progress newer run and older runs do not.
    runs = [
        _run(5, 1, "Connector", "", "in_progress"),
        _run(4, 1, "Connector", "failure"),
        _run(3, 1, "Connector", "success"),
    ]
    api = FakeApi([REPO], {"Org/demo": runs})
    results, failures = nightly_health.audit(api, "Org", NOW)
    assert failures == []
    (result,) = results
    assert (result.action, result.jobs) == ("opened", ["pipeline / publish-docker"])
    (issue,) = api.issues["Org/demo"]
    assert issue["title"] == "Nightly Connector failing" and issue["labels"] == ["nightly-red"]
    assert "https://github.com/Org/demo/actions/runs/4" in issue["body"]
    assert "- pipeline / publish-docker" in issue["body"]
    assert "[pipeline / publish-docker] Because there is no version of demo==0.3.9" in issue["body"]
    assert "Process completed" not in issue["body"]
    assert api.labels["Org/demo"] == {"nightly-red"}
    report = nightly_health.summary(results, failures)
    assert "| Org/demo | Connector | failure |" in report and "1 red" in report


@pytest.mark.spec("PIPE-GATES-R103")
def test_a_still_red_nightly_updates_the_same_issue() -> None:
    existing = {
        "number": 3,
        "state": "open",
        "title": "Nightly Connector failing",
        "body": "old",
        "html_url": "https://github.com/Org/demo/issues/3",
    }
    api = FakeApi([REPO], {"Org/demo": [_run(4, 1, "Connector", "timed_out")]}, {"Org/demo": [existing]})
    (result,), _ = nightly_health.audit(api, "Org", NOW)
    assert result.action == "updated" and result.issue_url.endswith("/issues/3")
    assert [w[0] for w in api.writes] == ["PATCH"]
    assert "ended `timed_out`" in existing["body"]


@pytest.mark.spec("PIPE-GATES-R103")
def test_a_green_nightly_closes_the_issue_and_another_conclusion_leaves_it() -> None:
    existing = {
        "number": 3,
        "state": "open",
        "title": "Nightly Connector failing",
        "body": "old",
        "html_url": "https://github.com/Org/demo/issues/3",
    }
    api = FakeApi([REPO], {"Org/demo": [_run(6, 1, "Connector", "success")]}, {"Org/demo": [existing]})
    (result,), _ = nightly_health.audit(api, "Org", NOW)
    assert result.action == "closed"
    assert existing["state"] == "closed"
    assert api.writes[0][1] == "/repos/Org/demo/issues/3/comments"
    cancelled = FakeApi(
        [REPO], {"Org/demo": [_run(7, 1, "Connector", "cancelled")]}, {"Org/demo": [dict(existing, state="open")]}
    )
    (other,), _ = nightly_health.audit(cancelled, "Org", NOW)
    assert other.action == "" and cancelled.writes == []
    # A run of a disabled workflow is not reported.
    disabled = FakeApi([REPO], {"Org/demo": [_run(8, 2, "Old", "failure")]})
    assert nightly_health.audit(disabled, "Org", NOW) == ([], [])


@pytest.mark.spec("PIPE-GATES-R103")
def test_archived_repositories_and_disabled_issues_are_not_written() -> None:
    repos = [
        {"full_name": "Org/gone", "archived": True, "has_issues": True},
        {"full_name": "Org/quiet", "archived": False, "has_issues": False},
    ]
    runs = {"Org/gone": [_run(1, 1, "Connector", "failure")], "Org/quiet": [_run(2, 1, "Connector", "failure")]}
    api = FakeApi(repos, runs)
    results, failures = nightly_health.audit(api, "Org", NOW)
    assert [(r.repo, r.action) for r in results] == [("Org/quiet", "issues disabled")]
    assert api.writes == [] and failures == []


@pytest.mark.spec("PIPE-GATES-R103")
def test_error_lines_drop_timestamps_and_put_generic_exit_lines_last() -> None:
    assert nightly_health.error_lines(LOG) == ["Because there is no version of demo==0.3.9"]
    only_generic = "2026-11-16T13:42:15.2Z ##[error]Process completed with exit code 1.\n"
    assert nightly_health.error_lines(only_generic) == ["Process completed with exit code 1."]


@pytest.mark.spec("PIPE-GATES-R103")
def test_the_workflow_is_scheduled_and_uses_an_existing_token() -> None:
    document = yaml.safe_load((ROOT / ".github/workflows/nightly_health.yml").read_text(encoding="utf-8"))
    assert document["name"] == "nightly-health"
    triggers = document[True]
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert document["permissions"] == {"contents": "read", "issues": "write"}
    step = document["jobs"]["health"]["steps"][-1]
    # The organization token the ruleset audit already uses; never a merge or push token.
    assert step["env"]["GH_TOKEN"] == "${{ secrets.RULESET_AUDIT_TOKEN || github.token }}"
    assert step["run"] == 'python3 -I scripts/nightly_health.py --org "$ORG"'
