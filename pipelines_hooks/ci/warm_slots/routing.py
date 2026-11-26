"""warm-slot-routing: pull requests route safely and warm slots hold no release secret (PIPE-GATES-R074).

A job runs on a warm slot when its ``runs-on`` names the slot label (default
``warm-slot``). Same-repository pull requests run there; a fork pull request
never does, because a fork controls the code the slot would run. Warm-slot
jobs keep no release credentials: no secret other than the automatic token,
no inherited secrets and no deployment environment. ``prune_to_budget``
trims a cache directory to the configured size, oldest files first.
"""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Mapping
from pathlib import Path

import yaml

from pipelines_hooks.core.errors import CannotRun

DEFAULT_LABEL = "warm-slot"
SAFE_SECRETS = frozenset({"GITHUB_TOKEN"})
SECRET_RE = re.compile(r"secrets\.([A-Za-z0-9_]+)")
SAME_REPOSITORY_RE = re.compile(
    r"github\.event\.pull_request\.head\.repo\.full_name\s*==\s*github\.repository"
    r"|github\.event\.pull_request\.head\.repo\.fork\s*==\s*false"
    r"|github\.event\.pull_request\.head\.repo\.fork\s*!=\s*true"
)
PULL_REQUEST_EVENTS = ("pull_request", "pull_request_target")


def _events(document: Mapping[object, object]) -> set[str]:
    # YAML 1.1 reads the key ``on`` as the boolean True.
    triggers = document.get("on", document.get(True))
    if isinstance(triggers, str):
        return {triggers}
    if isinstance(triggers, list):
        return {str(item) for item in triggers}
    return {str(key) for key in triggers} if isinstance(triggers, Mapping) else set()


def _labels(job: Mapping[object, object]) -> set[str]:
    runs_on = job.get("runs-on")
    if isinstance(runs_on, str):
        return {runs_on}
    if isinstance(runs_on, list):
        return {str(item) for item in runs_on}
    if isinstance(runs_on, Mapping):
        labels = runs_on.get("labels", ())
        return {labels} if isinstance(labels, str) else {str(item) for item in labels}
    return set()


def _secret_names(node: object) -> set[str]:
    if isinstance(node, str):
        return set(SECRET_RE.findall(node))
    if isinstance(node, Mapping):
        return set().union(*(_secret_names(value) for value in node.values())) if node else set()
    if isinstance(node, list):
        return set().union(*(_secret_names(value) for value in node)) if node else set()
    return set()


def check_routing(workflows: Mapping[str, object], label: str = DEFAULT_LABEL) -> list[str]:
    """Findings naming each ``<workflow>:<job>`` that breaks routing or credential isolation."""
    findings: list[str] = []
    for path, document in sorted(workflows.items()):
        if not isinstance(document, Mapping):
            continue
        events = _events(document)
        jobs = document.get("jobs")
        for name, job in sorted((jobs or {}).items()) if isinstance(jobs, Mapping) else ():
            if not isinstance(job, Mapping) or label not in _labels(job):
                continue
            subject = f"{path}:{name}"
            if "pull_request_target" in events:
                findings.append(f"{subject}: runs on a warm slot under pull_request_target, which a fork can trigger")
            elif "pull_request" in events and not SAME_REPOSITORY_RE.search(str(job.get("if", ""))):
                findings.append(
                    f"{subject}: can run a fork pull request on a warm slot; guard it to same-repository pull requests"
                )
            held = sorted(_secret_names(job) - SAFE_SECRETS)
            if held:
                findings.append(f"{subject}: a warm-slot job must not hold a release secret ({', '.join(held)})")
            if job.get("secrets") == "inherit":
                findings.append(f"{subject}: a warm-slot job must not inherit secrets")
            if job.get("environment"):
                findings.append(f"{subject}: a warm-slot job must not enter a deployment environment")
    return findings


def prune_to_budget(directory: Path, budget_bytes: int) -> int:
    """Delete the oldest files under ``directory`` until it fits ``budget_bytes``; returns the bytes freed."""
    if budget_bytes < 0:
        raise CannotRun("warm slots: the cache budget must not be negative")
    files = [
        (path.stat().st_mtime, path, path.stat().st_size)
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    ]
    total = sum(size for _, _, size in files)
    freed = 0
    for _, path, size in sorted(files, key=lambda item: (item[0], str(item[1]))):
        if total - freed <= budget_bytes:
            break
        os.unlink(path)
        freed += size
    return freed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="warm-slot-routing", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--label", default=DEFAULT_LABEL, help="the runner label that names a warm slot")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    workflows: dict[str, object] = {}
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        try:
            workflows[path.relative_to(root).as_posix()] = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise CannotRun(f"warm-slot-routing: cannot read {path.name}: {exc}") from None
    findings = check_routing(workflows, args.label)
    if findings:
        print("FAIL: warm-slot routing and credential isolation:")
        for finding in findings:
            print(f"    {finding}")
        return 1
    print("warm-slot-routing: OK: no fork pull request and no release secret reaches a warm slot")
    return 0
