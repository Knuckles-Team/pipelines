"""ci-gate-replica: every workflow and job classified, and external build tools installed."""

from __future__ import annotations

from tests.hooks.conftest import PYPROJECT, Repo

WORKFLOW = "on: push\njobs:\n  gates:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo gates\n  publish:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo publish\n"
REGISTRY = (
    PYPROJECT
    + '\n[tool.pipelines_hooks.ci_replica.workflows."release.yml"]\nblocking = true\nexecutable_jobs = ["gates"]\n'
    + '\n[tool.pipelines_hooks.ci_replica.workflows."release.yml".skip_reasons]\npublish = "tag-gated publishing never runs locally"\n'
)


def test_consistency_fires_on_an_unregistered_workflow_and_an_unclassified_job(repo: Repo) -> None:
    repo.commit({".github/workflows/release.yml": WORKFLOW})
    assert repo.run("ci-gate-replica", "--consistency-check") == 1
    repo.commit({"pyproject.toml": REGISTRY})
    assert repo.run("ci-gate-replica", "--consistency-check") == 0
    repo.commit({".github/workflows/release.yml": WORKFLOW + "  docs:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo docs\n"})
    assert repo.run("ci-gate-replica", "--consistency-check") == 1


def test_consistency_fires_on_a_cargo_wrapper_no_workflow_installs(repo: Repo) -> None:
    cargo_workflow = WORKFLOW.replace("echo gates", "cargo build")
    repo.commit({"pyproject.toml": REGISTRY, ".github/workflows/release.yml": cargo_workflow, ".cargo/config.toml": '[build]\nrustc-wrapper = "sccache"\n'})
    assert repo.run("ci-gate-replica", "--consistency-check") == 1


def test_replay_runs_executable_steps_and_reports_skipped_jobs(repo: Repo, capsys) -> None:
    repo.commit({"pyproject.toml": REGISTRY, ".github/workflows/release.yml": WORKFLOW})
    assert repo.run("ci-gate-replica") == 0
    output = capsys.readouterr().out
    assert "NOT VALIDATED LOCALLY" in output and "BLOCKING_FAIL=0" in output
    repo.commit({".github/workflows/release.yml": WORKFLOW.replace("echo gates", "exit 3")})
    assert repo.run("ci-gate-replica") == 1
