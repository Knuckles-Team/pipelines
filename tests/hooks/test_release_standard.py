"""release-standard warns by default and fails under --strict for a connector without Docker publish."""

from __future__ import annotations

import pytest

from tests.hooks import conftest
from tests.hooks.conftest import Repo

repo = conftest.repo

CONNECTOR = '[project]\nname = "x-mcp"\ndependencies = ["agent-connector-sdk>=0.3"]\n'
PIPELINE = (
    "jobs:\n  publish-pypi:\n    uses: Knuckles-Team/pipelines/.github/workflows/python_pipeline.yml@main\n"
    "  publish-docker:\n    uses: Knuckles-Team/pipelines/.github/workflows/container_pipeline.yml@main\n"
)


@pytest.mark.spec("PIPE-RELEASE-R013")
def test_a_connector_without_docker_publish_warns_and_fails_strict(repo: Repo, capsys) -> None:
    repo.commit({"pyproject.toml": CONNECTOR})
    assert repo.run("release-standard") == 0
    out = capsys.readouterr().out
    assert "docker/Dockerfile is not tracked" in out and "no enabled workflow job" in out
    assert repo.run("release-standard", "--strict") == 1


@pytest.mark.spec("PIPE-RELEASE-R013")
def test_a_conformant_connector_passes_strict(repo: Repo) -> None:
    repo.commit(
        {"pyproject.toml": CONNECTOR, "docker/Dockerfile": "FROM x\n", ".github/workflows/pipeline.yml": PIPELINE}
    )
    assert repo.run("release-standard", "--strict") == 0


@pytest.mark.spec("PIPE-RELEASE-R013")
def test_a_disabled_docker_job_is_flagged_and_a_non_connector_is_exempt(repo: Repo) -> None:
    disabled = PIPELINE.replace("  publish-docker:\n", "  publish-docker:\n    if: false\n")
    repo.commit(
        {"pyproject.toml": CONNECTOR, "docker/Dockerfile": "FROM x\n", ".github/workflows/pipeline.yml": disabled}
    )
    assert repo.run("release-standard", "--strict") == 1
    repo.commit({"pyproject.toml": '[project]\nname = "lib"\n'})
    assert repo.run("release-standard", "--strict") == 0
