"""The shared PR gate refuses a CI-skip marker in a pull request title or body (PIPE-GATES-R047)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

GATES_WORKFLOW = Path(__file__).parents[1] / ".github/workflows/gates_pipeline.yml"
CI_TEMPLATE = Path(__file__).parents[1] / "templates/workflows/ci.yml"


def _job() -> dict:
    return yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["ci-skip-marker"]


def _run(title: str, body: str) -> subprocess.CompletedProcess[str]:
    script = _job()["steps"][0]["run"]
    env = {**os.environ, "PR_TITLE": title, "PR_BODY": body}
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=False)


@pytest.mark.spec("PIPE-GATES-R047")
@pytest.mark.parametrize("marker", ["[skip ci]", "[ci skip]", "[no ci]", "[skip actions]", "[actions skip]", "[SKIP CI]"])
def test_a_marker_in_the_title_or_body_fails(marker: str) -> None:
    assert _run(f"fix: thing {marker}", "plain body").returncode == 1
    assert _run("fix: thing", f"first line\n\nbody {marker}\n").returncode == 1


@pytest.mark.spec("PIPE-GATES-R047")
def test_a_clean_title_and_body_pass() -> None:
    assert _run("fix: skip the cache when CI is cold", "Mentions ci and skip separately.").returncode == 0
    assert _run("fix: thing", "").returncode == 0


@pytest.mark.spec("PIPE-GATES-R047")
def test_the_job_runs_on_pull_requests_inside_the_shared_gates_workflow() -> None:
    job = _job()
    assert job["if"] == "github.event_name == 'pull_request'"
    assert job["permissions"] == {"contents": "read"}
    # The caller aggregate needs the reusable `gates` job, which fails when any job in it fails.
    needs = yaml.safe_load(CI_TEMPLATE.read_text(encoding="utf-8"))["jobs"]["ci-required"]["needs"]
    assert "gates" in needs
