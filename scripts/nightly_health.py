"""Report red scheduled runs across the organization as issues (PIPE-GATES-R103).

``python scripts/nightly_health.py --org OWNER`` lists every non-archived repository of the
organization and, per active workflow, its latest completed scheduled run of the last
``WINDOW_DAYS`` days. A red run (failure, timed out, startup failure) opens or updates one issue
in that repository titled ``Nightly <workflow> failing`` and labelled ``nightly-red``, with the
run link, the failing job names and the first ``##[error]`` lines of their logs. A green run
closes that issue. Other conclusions leave it as it is. The run writes one summary table to
``$GITHUB_STEP_SUMMARY`` and exits 1 only when it could not read the organization or could not
write an issue, so a token without the needed scope shows as a red run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

API = "https://api.github.com"
LABEL = "nightly-red"
RED = frozenset({"failure", "timed_out", "startup_failure"})
WINDOW_DAYS = 8
MAX_JOBS = 5
MAX_ERRORS = 10
MAX_LINE = 300
GENERIC = re.compile(r"Process completed with exit code \d+\.?$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ")
TRANSIENT = frozenset({500, 502, 503, 504})


class Api:
    """GitHub REST with a bearer token, bounded retries and no token on a redirect."""

    def __init__(self, token: str) -> None:
        self.token = token

    def call(self, method: str, path: str, data: dict | None = None, raw: bool = False) -> bytes | None:
        url = path if path.startswith("https://") else API + path
        body = None if data is None else json.dumps(data).encode()
        for attempt in range(4):
            request = urllib.request.Request(url, data=body, method=method)
            request.add_header("User-Agent", "nightly-health")
            request.add_header("Accept", "application/vnd.github+json")
            # Log downloads redirect to storage; the token must not follow the redirect.
            request.add_unredirected_header("Authorization", f"Bearer {self.token}")
            try:
                with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - https only
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code == 404 or (raw and error.code in {403, 410}):
                    return None
                if error.code not in TRANSIENT or attempt == 3:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise
            time.sleep(2 * 2**attempt)
        raise AssertionError("unreachable")

    def json(self, method: str, path: str, data: dict | None = None):
        body = self.call(method, path, data)
        return None if body is None else json.loads(body or b"null")

    def pages(self, path: str, key: str | None = None, limit: int = 10) -> list:
        items: list = []
        joiner = "&" if "?" in path else "?"
        for page in range(1, limit + 1):
            chunk = self.json("GET", f"{path}{joiner}per_page=100&page={page}")
            chunk = [] if chunk is None else (chunk[key] if key else chunk)
            items.extend(chunk)
            if len(chunk) < 100:
                break
        return items


@dataclass
class Result:
    repo: str
    workflow: str
    conclusion: str
    run_url: str
    issue_url: str = ""
    action: str = ""
    jobs: list[str] = field(default_factory=list)


def latest_scheduled(runs: list[dict], active: dict[int, str]) -> dict[int, dict]:
    """The newest completed scheduled run per active workflow; runs come newest first."""
    latest: dict[int, dict] = {}
    for run in runs:
        workflow = run.get("workflow_id")
        if workflow in active and workflow not in latest and run.get("status") == "completed":
            latest[workflow] = run
    return latest


def error_lines(log: str) -> list[str]:
    """The ##[error] lines of a job log without timestamps; generic exit-code lines go last."""
    found = []
    for line in log.splitlines():
        if "##[error]" in line:
            text = STAMP.sub("", line.lstrip("﻿")).replace("##[error]", "", 1).strip()
            found.append(text[:MAX_LINE])
    specific = [line for line in found if not GENERIC.search(line)]
    return specific or found


def issue_title(workflow: str) -> str:
    return f"Nightly {workflow} failing"


def issue_body(run: dict, jobs: list[str], errors: list[str]) -> str:
    job_lines = "\n".join(f"- {name}" for name in jobs) or "- (no failed job reported)"
    error_block = "\n".join(errors[:MAX_ERRORS]).replace("```", "'''") or "(no ##[error] line in the job logs)"
    return (
        f"The latest scheduled run of **{run['name']}** ended `{run['conclusion']}`.\n\n"
        f"- Run: {run['html_url']}\n"
        f"- Commit: `{run.get('head_sha', '')[:12]}` on `{run.get('head_branch') or ''}`\n"
        f"- Finished: {run.get('updated_at', '')}\n\n"
        f"Failing jobs:\n{job_lines}\n\n"
        f"First errors:\n```\n{error_block}\n```\n\n"
        "This issue is kept by the scheduled nightly-health workflow of Knuckles-Team/pipelines. "
        "It is updated while the scheduled run stays red and closed when it is green again.\n"
    )


def failed_jobs(api: Api, repo: str, run_id: int) -> tuple[list[str], list[str]]:
    jobs = api.pages(f"/repos/{repo}/actions/runs/{run_id}/jobs?filter=latest", "jobs", limit=3)
    failed = [job for job in jobs if job.get("conclusion") in RED]
    errors: list[str] = []
    for job in failed[:MAX_JOBS]:
        log = api.call("GET", f"/repos/{repo}/actions/jobs/{job['id']}/logs", raw=True)
        lines = error_lines(log.decode("utf-8", "replace")) if log else []
        errors.extend(f"[{job['name']}] {line}" for line in lines[:3])
    return [job["name"] for job in failed], errors


def ensure_label(api: Api, repo: str) -> None:
    if api.json("GET", f"/repos/{repo}/labels/{LABEL}") is None:
        api.json(
            "POST",
            f"/repos/{repo}/labels",
            {"name": LABEL, "color": "b60205", "description": "A scheduled workflow run is failing"},
        )


def open_issue(api: Api, repo: str, title: str) -> dict | None:
    query = urllib.parse.urlencode({"state": "open", "labels": LABEL})
    for issue in api.pages(f"/repos/{repo}/issues?{query}", limit=3):
        if issue.get("title") == title and "pull_request" not in issue:
            return issue
    return None


def report_red(api: Api, repo: str, run: dict, has_issues: bool) -> Result:
    jobs, errors = failed_jobs(api, repo, run["id"])
    result = Result(repo, run["name"], run["conclusion"], run["html_url"], jobs=jobs)
    if not has_issues:
        result.action = "issues disabled"
        return result
    title, body = issue_title(run["name"]), issue_body(run, jobs, errors)
    issue = open_issue(api, repo, title)
    if issue is None:
        ensure_label(api, repo)
        issue = api.json("POST", f"/repos/{repo}/issues", {"title": title, "body": body, "labels": [LABEL]})
        result.action = "opened"
    else:
        api.json("PATCH", f"/repos/{repo}/issues/{issue['number']}", {"body": body})
        result.action = "updated"
    result.issue_url = issue["html_url"]
    return result


def report_green(api: Api, repo: str, run: dict, has_issues: bool) -> Result | None:
    if not has_issues:
        return None
    issue = open_issue(api, repo, issue_title(run["name"]))
    if issue is None:
        return None
    number = issue["number"]
    api.json("POST", f"/repos/{repo}/issues/{number}/comments", {"body": f"Green again in {run['html_url']}; closing."})
    api.json("PATCH", f"/repos/{repo}/issues/{number}", {"state": "closed", "state_reason": "completed"})
    return Result(repo, run["name"], run["conclusion"], run["html_url"], issue["html_url"], "closed")


def check_repo(api: Api, repo: dict, since: str) -> list[Result]:
    name = repo["full_name"]
    workflows = api.json("GET", f"/repos/{name}/actions/workflows?per_page=100")
    active = {w["id"]: w["name"] for w in (workflows or {}).get("workflows", []) if w.get("state") == "active"}
    if not active:
        return []
    runs = api.pages(
        f"/repos/{name}/actions/runs?event=schedule&status=completed&created=%3E%3D{since}", "workflow_runs", 3
    )
    results = []
    for run in latest_scheduled(runs, active).values():
        if run["conclusion"] in RED:
            results.append(report_red(api, name, run, repo.get("has_issues", False)))
        elif run["conclusion"] == "success":
            closed = report_green(api, name, run, repo.get("has_issues", False))
            results.append(closed or Result(name, run["name"], "success", run["html_url"]))
        else:
            results.append(Result(name, run["name"], run["conclusion"], run["html_url"]))
    return results


def summary(results: list[Result], failures: list[str]) -> str:
    red = [r for r in results if r.conclusion in RED]
    closed = [r for r in results if r.action == "closed"]
    other = [r for r in results if r.conclusion not in RED and r.conclusion != "success"]
    lines = [
        "# Nightly health",
        "",
        f"{len(results)} scheduled workflows checked: {len(red)} red, {len(closed)} issues closed, "
        f"{len(other)} with another conclusion, {len(failures)} errors.",
        "",
    ]
    if red:
        lines += ["| Repository | Workflow | Conclusion | Run | Issue |", "|---|---|---|---|---|"]
        for r in sorted(red, key=lambda r: (r.repo, r.workflow)):
            issue = f"[{r.action}]({r.issue_url})" if r.issue_url else r.action
            lines.append(f"| {r.repo} | {r.workflow} | {r.conclusion} | [run]({r.run_url}) | {issue} |")
        lines.append("")
    if closed:
        lines += ["Closed (green again):", ""] + [f"- {r.repo}: [{r.workflow}]({r.issue_url})" for r in closed] + [""]
    if other:
        lines += ["Other conclusions (no issue change):", ""]
        lines += [f"- {r.repo}: [{r.workflow}]({r.run_url}) `{r.conclusion}`" for r in other] + [""]
    if failures:
        lines += ["Errors:", ""] + [f"- {failure}" for failure in failures] + [""]
    return "\n".join(lines)


def audit(api: Api, org: str, now: datetime) -> tuple[list[Result], list[str]]:
    since = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    results: list[Result] = []
    failures: list[str] = []
    for repo in api.pages(f"/orgs/{org}/repos?type=all&sort=full_name", limit=10):
        if repo.get("archived") or repo.get("disabled"):
            continue
        try:
            results.extend(check_repo(api, repo, since))
        except urllib.error.HTTPError as error:
            failures.append(f"{repo['full_name']}: HTTP {error.code} {error.reason}")
    return results, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="Knuckles-Team")
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN is required")
        return 1
    results, failures = audit(Api(token), args.org, datetime.now(UTC))
    report = summary(results, failures)
    print(report)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    for failure in failures:
        print(f"::error::{failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
