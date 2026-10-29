#!/usr/bin/env python3
"""Fail-closed, trusted gate for green pull requests (fleet auto-merge).

The reusable workflow auto_merge_pipeline.yml fetches this file from
Knuckles-Team/pipelines at main without checking out the pull request. All repository state used for the decision is read back
from GitHub's API, and the merge command receives only a validated PR number
and commit SHA.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

DEFAULT_REQUIRED_CHECK = "CI required"
BASE_BRANCH = "main"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

ApiGet = Callable[[str], Any]
Merge = Callable[[int, str], None]
Log = Callable[[str], None]


class GateNotReady(Exception):
    """A safe no-op: the PR is not eligible to arm auto-merge yet."""


class ApiFailure(Exception):
    """The API could not establish the safety preconditions."""


def _sha(value: object) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise GateNotReady("the candidate head is not a full commit SHA")
    return value.lower()


def _repo(value: object) -> str:
    if not isinstance(value, str) or REPO_RE.fullmatch(value) is None:
        raise ApiFailure("GITHUB_REPOSITORY is invalid")
    return value


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GateNotReady("the pull request number is invalid")
    return value


def github_get(path: str, *, api_url: str, token: str) -> Any:
    """Perform one authenticated GET; callers pass only fixed/validated paths."""

    request = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise ApiFailure(f"GitHub GET {path} returned HTTP {exc.code}: {detail}") from exc
    except (OSError, ValueError) as exc:
        raise ApiFailure(f"GitHub GET {path} failed: {exc}") from exc


def _get(api_get: ApiGet, path: str, log: Log) -> Any:
    log(f"GET {path}")
    return api_get(path)


def _pull_request(
    *,
    repo: str,
    number: int,
    api_get: ApiGet,
    log: Log,
) -> tuple[int, str]:
    payload = _get(api_get, f"/repos/{repo}/pulls/{number}", log)
    if not isinstance(payload, Mapping):
        raise ApiFailure("pull request API returned a non-object")
    if payload.get("state") != "open" or payload.get("draft") is not False:
        raise GateNotReady("pull request is closed or still a draft")
    base = payload.get("base")
    head = payload.get("head")
    if not isinstance(base, Mapping) or base.get("ref") != BASE_BRANCH:
        raise GateNotReady("pull request base is not main")
    base_repo = base.get("repo")
    if not isinstance(base_repo, Mapping) or base_repo.get("full_name") != repo:
        raise GateNotReady("pull request targets a different repository")
    if not isinstance(head, Mapping):
        raise GateNotReady("pull request head is missing")
    return number, _sha(head.get("sha"))


def _candidate_pr(
    *,
    event_name: str,
    event: Mapping[str, Any],
    repo: str,
    required_check: str,
    api_get: ApiGet,
    log: Log,
) -> tuple[int, str]:
    if event_name in ("pull_request", "pull_request_target"):
        return _pull_request(
            repo=repo,
            number=_positive_int(event.get("number")),
            api_get=api_get,
            log=log,
        )
    if event_name != "check_run":
        raise GateNotReady(f"event {event_name!r} is not an auto-merge trigger")
    check_run = event.get("check_run")
    if (
        not isinstance(check_run, Mapping)
        or check_run.get("name") != required_check
        or check_run.get("conclusion") != "success"
    ):
        raise GateNotReady(f"check_run event is not a successful {required_check!r}")
    head_sha = _sha(check_run.get("head_sha"))
    pulls = _get(
        api_get,
        f"/repos/{repo}/commits/{head_sha}/pulls?per_page=100",
        log,
    )
    if not isinstance(pulls, list):
        raise ApiFailure("commit pull request API returned a non-list")
    matches = [
        pull
        for pull in pulls
        if isinstance(pull, Mapping)
        and pull.get("state") == "open"
        and pull.get("draft") is False
        and isinstance(pull.get("base"), Mapping)
        and pull["base"].get("ref") == BASE_BRANCH
        and isinstance(pull.get("head"), Mapping)
        and _same_sha(pull["head"].get("sha"), head_sha)
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("number"), int):
        raise GateNotReady("the check-run SHA does not identify one open main PR")
    return _pull_request(
        repo=repo,
        number=matches[0]["number"],
        api_get=api_get,
        log=log,
    )


def _same_sha(value: object, expected: str) -> bool:
    return isinstance(value, str) and value.lower() == expected


def _required_contexts(payload: object) -> set[str]:
    if not isinstance(payload, Mapping):
        raise ApiFailure("required-status-check API returned a non-object")
    contexts = {value for value in payload.get("contexts", []) if isinstance(value, str)}
    checks = payload.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, Mapping) and isinstance(check.get("context"), str):
                contexts.add(check["context"])
    return contexts


def _classic_contexts(*, repo: str, api_get: ApiGet, log: Log) -> set[str]:
    """Required contexts from classic branch protection; empty when it does not apply."""
    path = f"/repos/{repo}/branches/{BASE_BRANCH}"
    try:
        payload = _get(api_get, path, log)
    except ApiFailure as exc:
        if "HTTP 404" in str(exc):
            return set()
        raise
    if not isinstance(payload, Mapping):
        raise ApiFailure("branch API returned a non-object")
    protection = payload.get("protection")
    if payload.get("protected") is not True or not isinstance(protection, Mapping):
        return set()
    required = protection.get("required_status_checks")
    if not isinstance(required, Mapping):
        return set()
    enforcement = required.get("enforcement_level")
    if not isinstance(enforcement, str) or enforcement == "off":
        return set()
    return _required_contexts(required)


def _ruleset_contexts(*, repo: str, api_get: ApiGet, log: Log) -> set[str]:
    """Required contexts from the active repository rulesets that apply to main."""
    path = f"/repos/{repo}/rules/branches/{BASE_BRANCH}?per_page=100"
    try:
        payload = _get(api_get, path, log)
    except ApiFailure as exc:
        if "HTTP 404" in str(exc):
            return set()
        raise
    if not isinstance(payload, list):
        raise ApiFailure("branch rules API returned a non-list")
    contexts: set[str] = set()
    for rule in payload:
        if not isinstance(rule, Mapping) or rule.get("type") != "required_status_checks":
            continue
        parameters = rule.get("parameters")
        checks = parameters.get("required_status_checks") if isinstance(parameters, Mapping) else None
        if isinstance(checks, list):
            contexts |= {c["context"] for c in checks if isinstance(c, Mapping) and isinstance(c.get("context"), str)}
    return contexts


def _check_required_rule(*, repo: str, required_check: str, api_get: ApiGet, log: Log) -> None:
    """Fail closed unless main requires ``required_check`` through classic protection or a ruleset."""
    contexts = _classic_contexts(repo=repo, api_get=api_get, log=log) | _ruleset_contexts(
        repo=repo, api_get=api_get, log=log
    )
    log(f"required status-check contexts: {sorted(contexts)!r}")
    if not contexts:
        raise GateNotReady("main has no required status check (classic protection or ruleset)")
    if required_check not in contexts:
        raise GateNotReady(f"required context {required_check!r} is absent; observed {sorted(contexts)!r}")


def _required_check_passed(*, repo: str, required_check: str, head_sha: str, api_get: ApiGet, log: Log) -> None:
    quoted = urllib.parse.quote(required_check, safe="")
    path = f"/repos/{repo}/commits/{head_sha}/check-runs?check_name={quoted}&per_page=100"
    payload = _get(api_get, path, log)
    if not isinstance(payload, Mapping):
        raise ApiFailure("check-runs API returned a non-object")
    runs = payload.get("check_runs")
    if not isinstance(runs, list):
        raise ApiFailure("check-runs API returned no check_runs list")
    matches = [
        run
        for run in runs
        if isinstance(run, Mapping)
        and run.get("name") == required_check
        and _same_sha(run.get("head_sha"), head_sha)
        and isinstance(run.get("id"), int)
    ]
    if not matches:
        raise GateNotReady(f"no {required_check!r} check run exists for this head")
    latest = max(matches, key=lambda run: run["id"])
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise GateNotReady(f"the latest {required_check!r} check run is not success")
    log(f"{required_check!r} success matches head {head_sha}")


def run_gate(
    *,
    event_name: str,
    event: Mapping[str, Any],
    repo: str,
    api_get: ApiGet,
    merge: Merge,
    required_check: str = DEFAULT_REQUIRED_CHECK,
    log: Log = print,
) -> None:
    if not required_check.strip():
        raise GateNotReady("no required check name is configured")
    number, head_sha = _candidate_pr(
        event_name=event_name,
        event=event,
        repo=repo,
        required_check=required_check,
        api_get=api_get,
        log=log,
    )
    _check_required_rule(repo=repo, required_check=required_check, api_get=api_get, log=log)
    if event_name == "check_run":
        _required_check_passed(
            repo=repo,
            required_check=required_check,
            head_sha=head_sha,
            api_get=api_get,
            log=log,
        )
    # On a pull_request event the check has not run yet. GitHub's native auto-merge
    # (--auto --match-head-commit) waits for every required check, and the rule check
    # above refuses unless main requires the configured check, so arming here cannot
    # merge anything that has not passed CI. check_run events from Actions-created
    # check runs never start workflows, so arming on the PR event is what works.
    log(f"arming auto-merge for PR {number} at exact head {head_sha}")
    merge(number, head_sha)


def _gh_merge(number: int, head_sha: str, *, repo: str, token: str) -> None:
    if not token:
        raise ApiFailure("MERGE_TOKEN is empty")
    command = [
        "gh",
        "pr",
        "merge",
        "--auto",
        "--merge",
        "--match-head-commit",
        head_sha,
        str(number),
    ]
    environment = os.environ.copy()
    environment.update({"GH_REPO": repo, "GH_TOKEN": token})
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ApiFailure(f"gh pr merge --auto exited {result.returncode}: {detail or '(no output)'}")


def main() -> int:
    try:
        event_path = os.environ["GITHUB_EVENT_PATH"]
        with open(event_path, encoding="utf-8") as stream:
            event = json.load(stream)
        run_gate(
            event_name=os.environ["GITHUB_EVENT_NAME"],
            event=event,
            repo=_repo(os.environ["GITHUB_REPOSITORY"]),
            required_check=os.environ.get("REQUIRED_CHECK", DEFAULT_REQUIRED_CHECK),
            api_get=lambda path: github_get(
                path,
                api_url=os.environ["GITHUB_API_URL"],
                token=os.environ["GITHUB_TOKEN"],
            ),
            merge=lambda number, sha: _gh_merge(
                number,
                sha,
                repo=os.environ["GITHUB_REPOSITORY"],
                token=os.environ["MERGE_TOKEN"],
            ),
        )
    except GateNotReady as exc:
        print(f"auto-merge not armed: {exc}")
    except (ApiFailure, KeyError, json.JSONDecodeError) as exc:
        print(f"auto-merge gate failed closed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
