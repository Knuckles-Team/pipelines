"""The central connector pipeline and its one caller template (PIPE-RELEASE-R018)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
CENTRAL = ROOT / ".github/workflows/connector_pipeline.yml"
CALLER = ROOT / "templates/workflows/connector.yml"
TAG = "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"
MAIN = "github.event_name == 'push' && github.ref == 'refs/heads/main'"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(document: dict) -> dict:
    return document.get(True, document.get("on"))


def _jobs() -> dict:
    return _load(CENTRAL)["jobs"]


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_central_pipeline_routes_each_event_to_its_jobs() -> None:
    jobs = _jobs()
    assert jobs["pr"]["if"] == "github.event_name == 'pull_request'"
    assert jobs["pr"]["uses"].endswith("/connector_pr_pipeline.yml@main")
    for name, workflow in (("org-site", "notify_org_site"), ("main", "main_pipeline")):
        assert jobs[name]["if"] == MAIN
        assert jobs[name]["uses"].endswith(f"/{workflow}.yml@main")
    assert jobs["main"]["with"]["backward-python"] == "${{ inputs.backward-python }}"
    assert _on(_load(CENTRAL))["workflow_call"]["inputs"]["backward-python"]["default"] == "3.12"
    rebuild = jobs["sdk-rebuild"]
    assert rebuild["uses"].endswith("/connector_sdk_rebuild_pipeline.yml@main")
    for event in ("schedule", "repository_dispatch", "workflow_dispatch"):
        assert f"github.event_name == '{event}'" in rebuild["if"]


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_nothing_publishes_on_a_main_push_and_a_v_tag_publishes() -> None:
    jobs = _jobs()
    publishers = {
        "publish-pypi": "python_pipeline",
        "publish-docker": "container_pipeline",
        "publish-pages": "pages_pipeline",
    }
    for name, workflow in publishers.items():
        assert jobs[name]["uses"].endswith(f"/{workflow}.yml@main")
        assert jobs[name]["if"].startswith(TAG), name
        assert "refs/heads/main" not in jobs[name]["if"]
    assert jobs["publish-pypi"]["with"]["require-tag"] is True
    assert jobs["publish-docker"]["needs"] == "publish-pypi"
    for name in ("pr", "org-site", "main", "sdk-rebuild"):
        assert jobs[name]["uses"].split("/")[-1].split("@")[0] not in {f"{w}.yml" for w in publishers.values()}


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_container_pipeline_publishes_on_main_or_a_v_tag_ref() -> None:
    text = (ROOT / ".github/workflows/container_pipeline.yml").read_text(encoding="utf-8")
    assert "startsWith(github.ref, 'refs/tags/v')" in text
    assert "github.ref == 'refs/heads/main' && " not in text.replace("(github.ref == 'refs/heads/main' ||", "")


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_central_pipeline_has_ci_required_and_read_only_workflow_permissions() -> None:
    document = _load(CENTRAL)
    assert document["permissions"] == {"contents": "read"}
    required = document["jobs"]["ci-required"]
    assert required["name"] == "CI required"
    assert required["if"] == "always()"
    routed = set(document["jobs"]) - {"ci-required"}
    assert set(required["needs"]) == routed
    writers = {
        name
        for name, job in document["jobs"].items()
        if any(scope == "write" for scope in job.get("permissions", {}).values())
    }
    assert writers == {"publish-pypi", "publish-pages"}
    text = CENTRAL.read_text(encoding="utf-8")
    assert "pull_request_target" not in text and "secrets: inherit" not in text


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_one_caller_template_triggers_every_route_without_top_level_write() -> None:
    document = _load(CALLER)
    triggers = _on(document)
    assert set(triggers) == {"pull_request", "push", "schedule", "repository_dispatch", "workflow_dispatch"}
    assert triggers["push"]["branches"] == ["main"] and triggers["push"]["tags"] == ["v*"]
    assert triggers["repository_dispatch"]["types"] == ["sdk-release"]
    assert document["permissions"] == {}
    pipeline = document["jobs"]["pipeline"]
    assert pipeline["uses"] == "Knuckles-Team/pipelines/.github/workflows/connector_pipeline.yml@main"
    assert pipeline["permissions"] == {
        "contents": "write",
        "pages": "write",
        "id-token": "write",
    }
    assert "pull_request_target" not in CALLER.read_text(encoding="utf-8")
    assert "inherit" not in CALLER.read_text(encoding="utf-8")
    required = document["jobs"]["ci-required"]
    assert required["name"] == "CI required" and required["needs"] == ["pipeline"]


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_caller_passes_exactly_the_secrets_the_central_workflow_declares() -> None:
    declared = set(_on(_load(CENTRAL))["workflow_call"]["secrets"])
    passed = set(_load(CALLER)["jobs"]["pipeline"]["secrets"])
    assert passed == declared
    inputs = set(_on(_load(CENTRAL))["workflow_call"]["inputs"])
    assert set(_load(CALLER)["jobs"]["pipeline"]["with"]) <= inputs


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_no_release_job_no_git_token_and_no_branch_push() -> None:
    document = _load(CENTRAL)
    assert {"release", "release-sync"}.isdisjoint(document["jobs"])
    workflow_call = _on(document)["workflow_call"]
    assert "release" not in workflow_call["inputs"] and "GIT_TOKEN" not in workflow_call["secrets"]
    assert "GIT_TOKEN" not in CENTRAL.read_text(encoding="utf-8")
    assert "GIT_TOKEN" not in CALLER.read_text(encoding="utf-8")
    caller = _load(CALLER)
    assert "release" not in _on(caller)["workflow_dispatch"]["inputs"]
    assert "release" not in caller["jobs"]["pipeline"]["with"]
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            assert "git push" not in step.get("run", "")


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_publish_stamps_the_tag_version_before_any_release_check() -> None:
    jobs = _jobs()
    assert jobs["publish-pypi"]["with"]["stamp-version-from-tag"] is True
    assert jobs["publish-docker"]["with"]["stamp_version_from_tag"] is True
    for workflow, key, anchor in (
        ("python_pipeline.yml", "publish-pypi", "Verify release version"),
        ("container_pipeline.yml", "publish-docker", "Validate reviewed release repair request"),
    ):
        steps = _load(ROOT / ".github/workflows" / workflow)["jobs"][key]["steps"]
        names = [step.get("name") for step in steps]
        stamp = steps[names.index("Stamp the tag version")]
        assert names.index("Stamp the tag version") < names.index(anchor)
        assert "startsWith(github.ref, 'refs/tags/v')" in stamp["if"]
        assert 'pipelines-connector version --root . set "$version"' in stamp["run"]
