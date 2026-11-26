"""Pull request routing, credential isolation and the cache budget (PIPE-GATES-R074)."""

from __future__ import annotations

import os

import pytest
import yaml
from pipelines_hooks.ci.warm_slots.routing import check_routing, prune_to_budget
from pipelines_hooks.cli import run_gate

SAME_REPOSITORY = "github.event.pull_request.head.repo.full_name == github.repository"


def _workflow(text: str) -> dict[str, object]:
    return {"ci.yml": yaml.safe_load(text)}


SAFE = f"""
on: [pull_request]
jobs:
  build:
    if: {SAME_REPOSITORY}
    runs-on: [self-hosted, warm-slot]
    steps:
      - run: echo ${{{{ secrets.GITHUB_TOKEN }}}}
  fork-safe:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{{{ secrets.PYPI_TOKEN }}}}
"""


@pytest.mark.spec("PIPE-GATES-R074")
def test_a_fork_pull_request_never_runs_on_a_warm_slot() -> None:
    assert check_routing(_workflow(SAFE)) == []
    unguarded = SAFE.replace(f"    if: {SAME_REPOSITORY}\n", "")
    assert check_routing(_workflow(unguarded)) == [
        "ci.yml:build: can run a fork pull request on a warm slot; guard it to same-repository pull requests"
    ]
    target = SAFE.replace("[pull_request]", "[pull_request_target]")
    assert "ci.yml:build: runs on a warm slot under pull_request_target, which a fork can trigger" in check_routing(
        _workflow(target)
    )
    push_only = SAFE.replace("[pull_request]", "[push]").replace(f"    if: {SAME_REPOSITORY}\n", "")
    assert check_routing(_workflow(push_only)) == []


@pytest.mark.spec("PIPE-GATES-R074")
def test_a_warm_slot_job_holds_no_release_secret(tmp_path, capsys) -> None:
    leaking = SAFE.replace("secrets.GITHUB_TOKEN", "secrets.PYPI_TOKEN")
    assert check_routing(_workflow(leaking)) == [
        "ci.yml:build: a warm-slot job must not hold a release secret (PYPI_TOKEN)"
    ]
    inherit = SAFE.replace(
        "    runs-on: [self-hosted, warm-slot]\n",
        "    runs-on: [self-hosted, warm-slot]\n    secrets: inherit\n    environment: release\n",
    )
    findings = check_routing(_workflow(inherit))
    assert "ci.yml:build: a warm-slot job must not inherit secrets" in findings
    assert "ci.yml:build: a warm-slot job must not enter a deployment environment" in findings
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(leaking, encoding="utf-8")
    assert run_gate("warm-slot-routing", ["--root", str(tmp_path)]) == 1
    assert "ci.yml:build" in capsys.readouterr().out
    (workflows / "ci.yml").write_text(SAFE, encoding="utf-8")
    assert run_gate("warm-slot-routing", ["--root", str(tmp_path)]) == 0


@pytest.mark.spec("PIPE-GATES-R074")
def test_the_target_dir_is_pruned_when_over_budget(tmp_path) -> None:
    target = tmp_path / "target"
    for index in range(4):
        path = target / "debug" / f"artifact-{index}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 100)
        os.utime(path, (1000 + index, 1000 + index))
    assert prune_to_budget(target, 400) == 0
    assert prune_to_budget(target, 250) == 200
    assert sorted(path.name for path in target.rglob("artifact-*")) == ["artifact-2", "artifact-3"]
    assert prune_to_budget(target, 0) == 200
    assert not list(target.rglob("artifact-*"))
