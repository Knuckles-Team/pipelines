"""release-standard enforces a tracked or centrally rendered connector Docker publish."""

from __future__ import annotations

import pytest

from tests.hooks import conftest
from tests.hooks.conftest import Repo

repo = conftest.repo

CONNECTOR = '[project]\nname = "x-mcp"\n[project.entry-points."scion_sdk.connector"]\nx-mcp = "x_mcp"\n'
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
def test_a_generated_connector_passes_strict_with_the_central_renderer(repo: Repo) -> None:
    repo.commit({"pyproject.toml": CONNECTOR, ".github/workflows/pipeline.yml": PIPELINE})
    assert repo.run("release-standard", "--strict") == 0


@pytest.mark.spec("PIPE-RELEASE-R013")
def test_a_custom_dockerfile_must_be_tracked_when_selected(repo: Repo) -> None:
    custom = PIPELINE.replace(
        "  publish-docker:\n", "  publish-docker:\n    with:\n      dockerfile: docker/custom.Dockerfile\n"
    )
    repo.commit(
        {"pyproject.toml": CONNECTOR, "docker/custom.Dockerfile": "FROM x\n", ".github/workflows/pipeline.yml": custom}
    )
    assert repo.run("release-standard", "--strict") == 0
    repo.commit({"docker/Dockerfile": "FROM default\n"})
    assert repo.run("release-standard", "--strict") == 0
    (repo.root / "docker/custom.Dockerfile").unlink()
    repo.git("add", "-u", "--", "docker/custom.Dockerfile")
    repo.git("commit", "-q", "-m", "remove custom recipe")
    assert repo.run("release-standard", "--strict") == 1


@pytest.mark.spec("PIPE-RELEASE-R013")
def test_a_disabled_docker_job_is_flagged_and_a_non_connector_is_exempt(repo: Repo) -> None:
    disabled = PIPELINE.replace("  publish-docker:\n", "  publish-docker:\n    if: false\n")
    repo.commit(
        {"pyproject.toml": CONNECTOR, "docker/Dockerfile": "FROM x\n", ".github/workflows/pipeline.yml": disabled}
    )
    assert repo.run("release-standard", "--strict") == 1
    repo.commit({"pyproject.toml": '[project]\nname = "lib"\n'})
    assert repo.run("release-standard", "--strict") == 0


@pytest.mark.spec("PIPE-RELEASE-R013")
def test_a_connector_is_detected_by_entry_point_or_sources_module_not_by_dependency_or_manifest(repo: Repo) -> None:
    sdk_only = '[project]\nname = "x"\ndependencies = ["scion-sdk>=0.4"]\n'
    repo.commit({"pyproject.toml": sdk_only, "connector_manifest.yml": "connector: x\n"})
    assert repo.run("release-standard", "--strict") == 0
    repo.commit({"pyproject.toml": sdk_only, "x/connector_sources.py": 'CONNECTOR = "x"\n'})
    assert repo.run("release-standard", "--strict") == 1
    repo.commit({".github/workflows/pipeline.yml": PIPELINE})
    assert repo.run("release-standard", "--strict") == 0


NPM_LANE = (
    "jobs:\n  release:\n    uses: Knuckles-Team/pipelines/.github/workflows/npm_pipeline.yml@main\n"
    "    with:\n      publish: true\n"
)
GOOD_PACKAGE = '{"name": "@knuckles-team/x", "version": "0.1.0", "publishConfig": {"access": "public"}}'


@pytest.mark.spec("PIPE-RELEASE-R033.1")
def test_an_npm_package_must_be_scoped_and_public(repo: Repo, capsys) -> None:
    repo.commit({"package.json": '{"name": "x", "version": "0.1.0"}', ".github/workflows/r.yml": NPM_LANE})
    assert repo.run("release-standard", "--strict") == 1
    out = capsys.readouterr().out
    assert "must be scoped @knuckles-team/" in out and 'publishConfig.access must be "public"' in out
    repo.commit({"package.json": GOOD_PACKAGE})
    assert repo.run("release-standard", "--strict") == 0


@pytest.mark.spec("PIPE-RELEASE-R033.5")
def test_a_publishable_npm_package_must_call_the_shared_lane(repo: Repo, capsys) -> None:
    repo.commit({"package.json": GOOD_PACKAGE})
    assert repo.run("release-standard") == 0
    assert "no enabled workflow job calls" in capsys.readouterr().out
    assert repo.run("release-standard", "--strict") == 1
    repo.commit({".github/workflows/r.yml": NPM_LANE.replace("publish: true", "publish: false")})
    assert repo.run("release-standard", "--strict") == 1
    repo.commit({".github/workflows/r.yml": NPM_LANE})
    assert repo.run("release-standard", "--strict") == 0


@pytest.mark.spec("PIPE-RELEASE-R033.5")
def test_a_private_package_is_exempt(repo: Repo) -> None:
    repo.commit({"package.json": '{"name": "app", "private": true}'})
    assert repo.run("release-standard", "--strict") == 0
