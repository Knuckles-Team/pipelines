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
    publishers = {"publish-pypi": "python_pipeline", "publish-docker": "container_pipeline", "publish-pages": "pages_pipeline"}
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
    assert writers == {"publish-pypi", "publish-pages", "release"}
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
    assert pipeline["permissions"] == {"contents": "write", "pages": "write", "id-token": "write", "checks": "read"}
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
def test_release_job_runs_only_on_a_release_dispatch_and_alone_writes_to_main() -> None:
    jobs = _jobs()
    release = jobs["release"]
    condition = release["if"]
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert "inputs.release != 'none'" in condition and "inputs.release_repair != true" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert release["permissions"] == {"contents": "write", "checks": "read"}
    assert "secrets.GIT_TOKEN" in CENTRAL.read_text(encoding="utf-8")
    # A release dispatch never also runs the SDK rebuild, and no other job but the publishers writes.
    assert "inputs.release == 'none'" in jobs["sdk-rebuild"]["if"]
    assert "release" in jobs["ci-required"]["needs"]
    inputs = _on(_load(CENTRAL))["workflow_call"]["inputs"]
    assert inputs["release"]["default"] == "none"
    assert "GIT_TOKEN" in _on(_load(CENTRAL))["workflow_call"]["secrets"]


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_release_job_refuses_red_main_and_an_existing_tag_then_pushes_the_tag() -> None:
    text = "\n".join(step.get("run", "") for step in _jobs()["release"]["steps"])
    assert '.name=="CI required"' in text and '!= success' in text and "refusing to release" in text
    assert 'ls-remote --exit-code --tags origin "refs/tags/v${version}"' in text
    assert "already exists" in text
    assert text.index("already exists") < text.index("git commit")
    assert text.index("git commit") < text.index('git tag -a "v${version}"') < text.index("git push")
    assert "chore(release): bump ${name} to ${version}" in text
    assert "Spec: none (release)\n" in text and "Co-Authored-By:" in text
    assert "pipelines-connector version" in text and "bump \"$LEVEL\"" in text


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_caller_exposes_the_release_choice_and_the_helper_dispatches_it() -> None:
    document = _load(CALLER)
    release = _on(document)["workflow_dispatch"]["inputs"]["release"]
    assert release["type"] == "choice" and release["default"] == "none"
    assert release["options"] == ["none", "patch", "minor", "major"]
    pipeline = document["jobs"]["pipeline"]
    assert pipeline["with"]["release"] == "${{ inputs.release || 'none' }}"
    assert pipeline["permissions"]["contents"] == "write" and pipeline["permissions"]["checks"] == "read"
    script = (ROOT / "scripts/release_connector.sh").read_text(encoding="utf-8")
    assert "gh workflow run connector.yml -R \"$repo\" -f \"release=$level\"" in script
    assert "patch|minor|major" in script
