"""Container callers retain legacy targets; opted-in bytes fail closed before build."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.workflow_fixtures import freeze_runtime, run_runtime_helper, runtime_case

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/container_pipeline.yml"
ACTION = ROOT / ".github/actions/stage-container-runtime/action.yml"


def _render_needed_step() -> dict:
    return next(
        step
        for step in yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
        if step.get("id") == "render-needed"
    )


def test_workflow_contract_and_legacy_publication_controls() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    job = workflow["jobs"]["publish-docker"]
    steps = job["steps"]
    checkout = next(step for step in steps if step["name"] == "Checkout pipeline contract")
    assert checkout["with"]["repository"] == "${{ job.workflow_repository }}"
    assert checkout["with"]["ref"] == "${{ job.workflow_sha }}"
    assert checkout["if"] == "steps.target.outputs.exists == 'true' && steps.target.outputs.runtime == 'true'"
    runtime = next(step for step in steps if step.get("id") == "runtime")
    assert runtime["if"] == checkout["if"]
    assert runtime["with"]["build-target"] == "${{ inputs.build_target }}"
    assert "build-target" in yaml.safe_load(ACTION.read_text())["inputs"]
    assert workflow["permissions"] == {"contents": "read"}
    assert job["runs-on"] == "self-hosted"
    assert job["strategy"]["matrix"]["include"] == [
        {"target": "agent", "suffix": "", "main_tag": "latest"},
        {"target": "mcp", "suffix": "-mcp", "main_tag": "mcp"},
    ]
    builds = [step for step in steps if "docker/build-push-action@" in step.get("uses", "")]
    assert len(builds) == 3 and builds[0]["with"] == builds[1]["with"] == builds[2]["with"]
    assert builds[0]["with"]["build-args"] == (
        "${{ steps.runtime.outputs.build-args }}\n${{ steps.render.outputs.build-args }}\n"
    )
    assert builds[0]["with"]["target"] == "${{ steps.target.outputs.target }}"
    assert builds[0]["with"]["push"] == "${{ github.event_name == 'push' || inputs.release_repair == true }}"
    assert steps.index(next(step for step in steps if step.get("id") == "runtime")) < steps.index(builds[0])
    assert steps.index(_render_needed_step()) < steps.index(next(step for step in steps if step.get("id") == "render"))
    assert steps.index(next(step for step in steps if step.get("id") == "render")) < steps.index(
        next(step for step in steps if step.get("id") == "target")
    )


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_main_connector_release_preflights_public_wheel_before_builder_or_login() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    inputs = workflow[True]["workflow_call"]["inputs"]
    assert inputs["published_wheel_distribution"]["default"] == ""
    assert inputs["published_wheel_module"]["default"] == ""
    assert inputs["published_wheel_extras"]["default"] == ""
    assert inputs["release_source_sha"]["type"] == "string" and inputs["release_source_sha"]["default"] == ""
    assert inputs["release_source_epoch"]["type"] == "string" and inputs["release_source_epoch"]["default"] == ""
    steps = workflow["jobs"]["publish-docker"]["steps"]
    identity = next(step for step in steps if step.get("id") == "published-wheel")
    guard = next(
        step for step in steps if step.get("name") == "Verify published connector wheel before container build"
    )
    builder = next(step for step in steps if step.get("id") == "builder")
    login = next(step for step in steps if "docker/login-action@" in step.get("uses", ""))
    builds = [step for step in steps if "docker/build-push-action@" in step.get("uses", "")]
    assert (
        identity["if"]
        == "(github.event_name == 'push' && github.ref == 'refs/heads/main' || inputs.release_repair == true) && steps.target.outputs.exists == 'true'"
    )
    assert "steps.published-wheel.outputs.connector == 'true'" in guard["if"]
    assert guard["uses"] == "./.pipeline-contract/.github/actions/verify-release-version"
    assert guard["with"] == {
        "mode": "published-wheel",
        "distribution": "${{ steps.published-wheel.outputs.distribution }}",
        "module": "${{ steps.published-wheel.outputs.module }}",
        "dockerfile": "${{ inputs.dockerfile }}",
        "extras": "${{ steps.published-wheel.outputs.extras }}",
        "root": "${{ steps.build-context.outputs.path }}",
    }
    assert guard["env"] == {"SOURCE_DATE_EPOCH": "${{ inputs.release_source_epoch }}"}
    assert steps.index(identity) < steps.index(guard) < steps.index(builder) < steps.index(login)
    assert steps.index(guard) < steps.index(builds[0])
    assert "--resolve-identity" in identity["run"]
    assert "--resolve-extras" in identity["run"]
    assert "MATRIX_TARGET" in identity["env"]
    assert "connector" in identity["run"]


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_reviewed_release_repair_is_opt_in_and_preflights_before_publish() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    inputs = workflow[True]["workflow_call"]["inputs"]
    repair = inputs["release_repair"]
    assert repair["type"] == "boolean" and repair["required"] is False and repair["default"] is False
    steps = workflow["jobs"]["publish-docker"]["steps"]
    validate = next(step for step in steps if step.get("name") == "Validate reviewed release repair request")
    source_checkout = next(step for step in steps if step.get("name") == "Checkout immutable release source")
    source_validation = next(
        step for step in steps if step.get("name") == "Validate immutable release source ancestry and epoch"
    )
    context = next(step for step in steps if step.get("id") == "build-context")
    checkout = next(step for step in steps if step.get("name") == "Checkout release guard contract")
    identity = next(step for step in steps if step.get("id") == "published-wheel")
    guard = next(
        step for step in steps if step.get("name") == "Verify published connector wheel before container build"
    )
    builder = next(step for step in steps if step.get("id") == "builder")
    login = next(step for step in steps if "docker/login-action@" in step.get("uses", ""))
    verify = next(step for step in steps if step.get("name") == "Verify the release artifacts")
    build = next(step for step in steps if step.get("id") == "buildx1")
    render_needed = next(step for step in steps if step.get("id") == "render-needed")
    render = next(step for step in steps if step.get("id") == "render")
    target = next(step for step in steps if step.get("id") == "target")
    version = next(step for step in steps if step.get("id") == "version")
    assert validate["if"] == "inputs.release_repair == true"
    assert source_checkout["if"] == source_validation["if"] == "inputs.release_repair == true"
    assert context["env"]["RELEASE_REPAIR"] == "${{ inputs.release_repair }}"
    assert source_checkout["with"] == {
        "repository": "${{ github.repository }}",
        "ref": "${{ inputs.release_source_sha }}",
        "fetch-depth": 0,
        "path": ".release-source",
        "persist-credentials": False,
    }
    assert "workflow_dispatch" in validate["run"]
    assert "refs/heads/main" in validate["run"]
    assert "git rev-parse --verify HEAD" in validate["run"]
    assert "git ls-remote origin refs/heads/main" in validate["run"]
    assert "canonical connector renderer" in validate["run"]
    assert validate["env"]["SOURCE_SHA"] == "${{ inputs.release_source_sha }}"
    assert validate["env"]["SOURCE_EPOCH"] == "${{ inputs.release_source_epoch }}"
    assert "merge-base --is-ancestor" in source_validation["run"]
    assert "--format=%ct" in source_validation["run"]
    assert context["id"] == "build-context"
    assert "context=.release-source" in context["run"]
    assert render_needed["env"]["BUILD_CONTEXT"] == "${{ steps.build-context.outputs.path }}"
    assert render["env"]["BUILD_CONTEXT"] == "${{ steps.build-context.outputs.path }}"
    assert target["env"]["BUILD_CONTEXT"] == "${{ steps.build-context.outputs.path }}"
    assert version["env"]["BUILD_CONTEXT"] == "${{ steps.build-context.outputs.path }}"
    assert verify["env"]["BUILD_CONTEXT"] == "${{ steps.build-context.outputs.path }}"
    assert build["with"]["context"] == "${{ steps.build-context.outputs.path }}"
    assert build["with"]["file"] == "${{ steps.build-context.outputs.dockerfile }}"
    assert "inputs.release_repair == true" in checkout["if"]
    assert "inputs.release_repair == true" in identity["if"]
    assert "inputs.release_repair == true" in guard["if"]
    assert "inputs.release_repair == true" in verify["if"]
    assert "inputs.release_repair == true" in build["with"]["push"]
    assert steps.index(validate) < steps.index(source_checkout) < steps.index(source_validation) < steps.index(context)
    assert steps.index(context) < steps.index(checkout) < steps.index(identity) < steps.index(guard)
    assert steps.index(guard) < steps.index(builder) < steps.index(login) < steps.index(build)
    assert steps.index(build) < steps.index(verify)
    assert "never republished" in repair["description"]


def test_repair_build_dockerfile_follows_immutable_context(tmp_path: Path) -> None:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
    context = next(step for step in steps if step.get("id") == "build-context")
    caller = tmp_path / "caller"
    source = tmp_path / ".release-source"
    (caller / "docker").mkdir(parents=True)
    (source / "docker").mkdir(parents=True)
    (caller / "docker/Dockerfile").write_text("FROM caller\n")
    (source / "docker/Dockerfile").write_text("FROM immutable-source\n")
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", "-c", context["run"]],
        cwd=caller,
        env={
            **os.environ,
            "GITHUB_OUTPUT": str(output),
            "INPUT_BUILD_CONTEXT": ".",
            "INPUT_DOCKERFILE": "docker/Dockerfile",
            "RELEASE_REPAIR": "true",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    selected = source / "docker/Dockerfile"
    assert values == {"path": ".release-source", "dockerfile": ".release-source/docker/Dockerfile"}
    assert selected.read_text() != (caller / "docker/Dockerfile").read_text()
    assert selected.read_text() == "FROM immutable-source\n"


def _run_repair_validation(
    tmp_path: Path,
    script: str,
    *,
    event: str = "workflow_dispatch",
    ref: str = "refs/heads/main",
    sha: str | None = None,
    render: str = "true",
) -> subprocess.CompletedProcess[str]:
    root = tmp_path / "source"
    root.mkdir(parents=True)
    (root / "README.md").write_text("reviewed\n")
    overridden = {
        "EVENT_NAME",
        "REF",
        "REVIEWED_SHA",
        "BUILD_CONTEXT",
        "DOCKERFILE",
        "BUILD_TARGET",
        "RENDER_CONNECTOR",
        "SOURCE_SHA",
        "SOURCE_EPOCH",
        "RUNTIME_INPUTS",
    }
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_") and key not in overridden}
    subprocess.run(["git", "init", "-q"], cwd=root, env=env, check=True)
    subprocess.run(["git", "add", "--", "README.md"], cwd=root, env=env, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        cwd=root,
        env=env,
        check=True,
    )
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, env=env, text=True).strip()
    epoch = subprocess.check_output(
        ["git", "show", "-s", "--format=%ct", current], cwd=root, env=env, text=True
    ).strip()
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], env=env, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=root, env=env, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:refs/heads/main"], cwd=root, env=env, check=True)
    result_env = {
        **env,
        "EVENT_NAME": event,
        "REF": ref,
        "REVIEWED_SHA": sha or current,
        "BUILD_CONTEXT": ".",
        "DOCKERFILE": "docker/Dockerfile",
        "BUILD_TARGET": "",
        "RENDER_CONNECTOR": render,
        "SOURCE_SHA": current,
        "SOURCE_EPOCH": epoch,
        "RUNTIME_INPUTS": "",
    }
    return subprocess.run(["bash", "-c", script], cwd=root, env=result_env, capture_output=True, text=True)


def _source_validation_fixture(
    tmp_path: Path, *, source_mode: str = "ancestor", epoch: str | None = None
) -> tuple[Path, str, str, str]:
    root = tmp_path / "current"
    root.mkdir(parents=True)
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}

    def git(*args: str, cwd: Path = root) -> str:
        return subprocess.check_output(["git", *args], cwd=cwd, env=git_env, text=True).strip()

    subprocess.run(["git", "init", "-q"], cwd=root, env=git_env, check=True)
    (root / "package.txt").write_text("released\n")
    subprocess.run(["git", "add", "--", "package.txt"], cwd=root, env=git_env, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "source"],
        cwd=root,
        env=git_env,
        check=True,
    )
    source_sha = git("rev-parse", "HEAD")
    (root / "workflow-only.txt").write_text("repair input\n")
    subprocess.run(["git", "add", "--", "workflow-only.txt"], cwd=root, env=git_env, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "workflow"],
        cwd=root,
        env=git_env,
        check=True,
    )
    reviewed_sha = git("rev-parse", "HEAD")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], env=git_env, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=root, env=git_env, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:refs/heads/main"], cwd=root, env=git_env, check=True)
    subprocess.run(
        ["git", "--git-dir", str(origin), "symbolic-ref", "HEAD", "refs/heads/main"], env=git_env, check=True
    )

    selected_sha = source_sha
    if source_mode == "unrelated":
        unrelated = tmp_path / "unrelated"
        subprocess.run(["git", "clone", "-q", str(origin), str(unrelated)], env=git_env, check=True)
        subprocess.run(["git", "checkout", "-q", "--orphan", "unrelated"], cwd=unrelated, env=git_env, check=True)
        subprocess.run(["git", "rm", "-q", "-rf", "."], cwd=unrelated, env=git_env, check=True)
        (unrelated / "other.txt").write_text("other\n")
        subprocess.run(["git", "add", "--", "other.txt"], cwd=unrelated, env=git_env, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "unrelated",
            ],
            cwd=unrelated,
            env=git_env,
            check=True,
        )
        selected_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=unrelated, env=git_env, text=True
        ).strip()
        subprocess.run(
            ["git", "push", "-q", "origin", "HEAD:refs/heads/unrelated"], cwd=unrelated, env=git_env, check=True
        )

    source_checkout = root / ".release-source"
    subprocess.run(["git", "clone", "-q", str(origin), str(source_checkout)], env=git_env, check=True)
    subprocess.run(["git", "checkout", "-q", selected_sha], cwd=source_checkout, env=git_env, check=True)
    selected_epoch = git("show", "-s", "--format=%ct", selected_sha, cwd=source_checkout)
    return root, reviewed_sha, selected_sha, epoch if epoch is not None else selected_epoch


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_reviewed_release_source_freeze_requires_ancestor_and_exact_epoch(tmp_path: Path) -> None:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
    script = next(step for step in steps if step.get("name") == "Validate immutable release source ancestry and epoch")[
        "run"
    ]
    root, reviewed_sha, source_sha, source_epoch = _source_validation_fixture(tmp_path / "valid")
    valid = subprocess.run(
        ["bash", "-c", script],
        cwd=root,
        env={
            **{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
            "REVIEWED_SHA": reviewed_sha,
            "SOURCE_SHA": source_sha,
            "SOURCE_EPOCH": source_epoch,
        },
        capture_output=True,
        text=True,
    )
    assert valid.returncode == 0, valid.stderr

    wrong_epoch_root, wrong_reviewed, wrong_source, _ = _source_validation_fixture(tmp_path / "epoch")
    wrong_epoch = subprocess.run(
        ["bash", "-c", script],
        cwd=wrong_epoch_root,
        env={
            **{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
            "REVIEWED_SHA": wrong_reviewed,
            "SOURCE_SHA": wrong_source,
            "SOURCE_EPOCH": "0",
        },
        capture_output=True,
        text=True,
    )
    assert wrong_epoch.returncode != 0
    assert "source epoch" in wrong_epoch.stdout + wrong_epoch.stderr

    unrelated_root, unrelated_reviewed, unrelated_source, unrelated_epoch = _source_validation_fixture(
        tmp_path / "unrelated", source_mode="unrelated"
    )
    unrelated = subprocess.run(
        ["bash", "-c", script],
        cwd=unrelated_root,
        env={
            **{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
            "REVIEWED_SHA": unrelated_reviewed,
            "SOURCE_SHA": unrelated_source,
            "SOURCE_EPOCH": unrelated_epoch,
        },
        capture_output=True,
        text=True,
    )
    assert unrelated.returncode != 0
    assert "not an ancestor" in unrelated.stdout + unrelated.stderr


@pytest.mark.spec("PIPE-RELEASE-R012.1")
@pytest.mark.parametrize(
    ("event", "ref", "expected_message"),
    [
        ("workflow_dispatch", "refs/heads/main", None),
        ("push", "refs/heads/main", "workflow_dispatch"),
        ("workflow_dispatch", "refs/heads/release", "refs/heads/main"),
    ],
)
def test_reviewed_release_repair_validation_accepts_only_current_main_dispatch(
    tmp_path: Path, event: str, ref: str, expected_message: str | None
) -> None:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
    script = next(step for step in steps if step.get("name") == "Validate reviewed release repair request")["run"]
    result = _run_repair_validation(tmp_path, script, event=event, ref=ref)
    assert (result.returncode == 0) == (expected_message is None), result.stderr
    if expected_message:
        assert expected_message in result.stdout + result.stderr


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_reviewed_release_repair_rejects_a_stale_or_noncanonical_source(tmp_path: Path) -> None:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
    script = next(step for step in steps if step.get("name") == "Validate reviewed release repair request")["run"]
    stale = _run_repair_validation(tmp_path / "stale", script, sha="0" * 40)
    assert stale.returncode != 0
    assert "does not equal github.sha" in stale.stdout + stale.stderr
    noncanonical = _run_repair_validation(tmp_path / "renderer", script, render="false")
    assert noncanonical.returncode != 0
    assert "canonical connector renderer" in noncanonical.stdout + noncanonical.stderr


def test_public_wheel_identity_step_skips_nonconnector_and_derives_connector(tmp_path: Path) -> None:
    step = next(
        step
        for step in yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
        if step.get("id") == "published-wheel"
    )
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}

    def commit_fixture(root: Path, pyproject: str, package: bool = False) -> None:
        root.mkdir()
        if package:
            (root / "demo").mkdir()
            (root / "demo/__init__.py").write_text("\n")
        (root / "pyproject.toml").write_text(pyproject)
        subprocess.run(["git", "init", "-q"], cwd=root, env=git_env, check=True)
        subprocess.run(["git", "add", "--", "."], cwd=root, env=git_env, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
            cwd=root,
            env=git_env,
            check=True,
        )

    cases = [
        (
            'name = "demo-dist"\nversion = "1.2.3"\n',
            {"connector": "false", "distribution": "", "module": ""},
        ),
        (
            '[project]\nname = "demo-dist"\nversion = "1.2.3"\n'
            '[project.entry-points."agent_connector_sdk.connector"]\n'
            'demo = "demo:connector"\n',
            {"connector": "true", "distribution": "demo-dist", "module": "demo"},
        ),
    ]
    for index, (pyproject, expected) in enumerate(cases):
        root = tmp_path / str(index)
        if not pyproject.startswith("[project]"):
            pyproject = "[project]\n" + pyproject
        commit_fixture(root, pyproject, package=index == 1)
        output = root / "output"
        environment = {
            **git_env,
            "BUILD_CONTEXT": ".",
            "PUBLISHED_WHEEL_DISTRIBUTION": "",
            "PUBLISHED_WHEEL_MODULE": "",
            "PUBLISHED_WHEEL_EXTRAS": "",
            "DOCKERFILE": "docker/Dockerfile",
            "MATRIX_TARGET": "mcp",
            "PUBLIC_WHEEL_GUARD": str(ROOT / ".github/actions/verify-release-version/public_wheel.py"),
            "GITHUB_OUTPUT": str(output),
        }
        result = subprocess.run(["bash", "-c", step["run"]], cwd=root, env=environment, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == expected | {"extras": ""}

    mismatch = {
        **environment,
        "PUBLISHED_WHEEL_EXTRAS": "mcp",
        "GITHUB_OUTPUT": str(tmp_path / "mismatch-output"),
    }
    result = subprocess.run(
        ["bash", "-c", step["run"]], cwd=tmp_path / "1", env=mismatch, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "do not match" in result.stdout + result.stderr

    repair_nonconnector = {
        **environment,
        "RELEASE_REPAIR": "true",
        "GITHUB_OUTPUT": str(tmp_path / "repair-nonconnector-output"),
    }
    result = subprocess.run(
        ["bash", "-c", step["run"]], cwd=tmp_path / "0", env=repair_nonconnector, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "requires a connector identity" in result.stdout + result.stderr


@pytest.mark.spec("PIPE-RELEASE-R001.13")
@pytest.mark.parametrize(
    ("pyproject", "dockerfile", "render_connector", "tracked", "expected"),
    [
        (
            '[project]\nname = "demo"\n[project.entry-points."agent_connector_sdk.connector"]\ndemo = "demo"\n',
            "docker/Dockerfile",
            "false",
            False,
            True,
        ),
        (
            '[project]\nname = "demo"\n[project.entry-points."agent_connector_sdk.connector"]\ndemo = "demo"\n',
            "docker/Dockerfile",
            "false",
            True,
            False,
        ),
        (
            '[project]\nname = "demo"\n[project.entry-points."agent_connector_sdk.connector"]\ndemo = "demo"\n',
            "custom/Dockerfile",
            "false",
            False,
            False,
        ),
        ('[project]\nname = "demo"\n', "docker/Dockerfile", "false", False, False),
        ('[project]\nname = "demo"\n', "custom/Dockerfile", "true", False, True),
    ],
)
def test_connector_render_is_selected_only_for_missing_canonical_dockerfile(
    tmp_path: Path,
    *,
    pyproject: str,
    dockerfile: str,
    render_connector: str,
    tracked: bool,
    expected: bool,
) -> None:
    step = _render_needed_step()
    (tmp_path / "pyproject.toml").write_text(pyproject)
    if tracked:
        recipe = tmp_path / dockerfile
        recipe.parent.mkdir(parents=True)
        recipe.write_text("FROM scratch\n")
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "BUILD_CONTEXT": ".",
            "DOCKERFILE": dockerfile,
            "RENDER_CONNECTOR": render_connector,
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text() == f"render={str(expected).lower()}\n"


def test_connector_sources_identity_enables_canonical_render(tmp_path: Path) -> None:
    step = _render_needed_step()
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    (tmp_path / "connector_sources.py").write_text('CONNECTOR = "demo"\n')
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=git_env, check=True)
    subprocess.run(
        ["git", "add", "--", "pyproject.toml", "connector_sources.py"], cwd=tmp_path, env=git_env, check=True
    )
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **git_env,
            "BUILD_CONTEXT": ".",
            "DOCKERFILE": "docker/Dockerfile",
            "RENDER_CONNECTOR": "false",
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text() == "render=true\n"


@pytest.mark.parametrize(
    ("requested", "leg", "dockerfile", "expected"),
    [
        ("", "agent", "FROM base AS agent\n", (True, "agent", False)),
        ("", "mcp", "FROM base AS agent\n", (False, None, False)),
        ("", "mcp", "from base as mcp\n", (True, "mcp", False)),
        ("", "agent", "FROM base AS agent\r\n", (True, "agent", False)),
        ("mcp", "mcp", "FROM base AS mcp\r\n", (True, "mcp", False)),
        ("default", "agent", "FROM base\n", (True, "", False)),
        ("default", "mcp", "FROM base\n", (False, None, False)),
        ("runtime", "agent", "FROM base AS runtime\n", (True, "runtime", False)),
        ("mcp", "mcp", "FROM base AS mcp\n", (True, "mcp", False)),
        ("mcp", "agent", "FROM base AS mcp\n", (False, None, False)),
        ("missing", "agent", "FROM base\n", (False, None, True)),
        ("bad;touch injected", "agent", "FROM base\n", (False, None, True)),
    ],
)
def test_target_selection(
    tmp_path: Path, *, requested: str, leg: str, dockerfile: str, expected: tuple[bool, str | None, bool]
) -> None:
    enabled, target, fails = expected
    step = next(
        step
        for step in yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
        if step.get("id") == "target"
    )
    recipe = tmp_path / "Dockerfile"
    recipe.write_text(dockerfile)
    output = tmp_path / "output"
    environment = {
        **os.environ,
        "BUILD_CONTEXT": ".",
        "DOCKERFILE": str(recipe),
        "GITHUB_OUTPUT": str(output),
        "REQUESTED_TARGET": requested,
        "MATRIX_TARGET": leg,
        "RUNTIME_REQUEST": "",
    }
    result = subprocess.run(["bash", "-c", step["run"]], env=environment, capture_output=True)
    assert (result.returncode != 0) == fails
    if not fails:
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        assert values["exists"] == str(enabled).lower()
        assert values.get("target") == target
        assert values["runtime"] == "false"


def test_missing_custom_dockerfile_fails_closed(tmp_path: Path) -> None:
    step = next(
        step
        for step in yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
        if step.get("id") == "target"
    )
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "BUILD_CONTEXT": ".",
            "DOCKERFILE": "custom/Dockerfile",
            "GITHUB_OUTPUT": str(output),
            "REQUESTED_TARGET": "",
            "MATRIX_TARGET": "agent",
            "RUNTIME_REQUEST": "",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "custom Dockerfile is absent" in result.stdout + result.stderr


def test_action_download_is_opt_in_same_run_and_before_verified_staging(tmp_path: Path) -> None:
    action = yaml.safe_load(ACTION.read_text())
    steps = action["runs"]["steps"]
    download = next(step for step in steps if "download-artifact@" in step.get("uses", ""))
    assert set(download["with"]) == {"artifact-ids", "path", "merge-multiple"}
    assert download["with"]["artifact-ids"] == "${{ inputs.artifact-id }}"
    assert steps.index(download) > steps.index(next(step for step in steps if step.get("id") == "request"))
    assert steps.index(download) < steps.index(next(step for step in steps if step.get("id") == "stage"))
    mode = steps[0]
    environment = {**os.environ, "PROFILE": "", "PROVENANCE": "", "GITHUB_OUTPUT": str(tmp_path / "mode")}
    subprocess.run(["bash", "-c", mode["run"]], env=environment, check=True)
    assert (tmp_path / "mode").read_text() == "enabled=false\n"
    environment["PROVENANCE"] = "1234"
    assert subprocess.run(["bash", "-c", mode["run"]], env=environment, capture_output=True).returncode != 0


def test_runtime_request_requires_explicit_target(tmp_path: Path) -> None:
    step = next(
        step
        for step in yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
        if step.get("id") == "target"
    )
    environment = {
        **os.environ,
        "DOCKERFILE": "absent",
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "REQUESTED_TARGET": "",
        "MATRIX_TARGET": "agent",
        "RUNTIME_REQUEST": "1234",
    }
    result = subprocess.run(["bash", "-c", step["run"]], env=environment, capture_output=True)
    assert result.returncode != 0
    assert (tmp_path / "output").read_text() == "runtime=true\n"


@pytest.mark.parametrize("collision", ["absent", "directory", "file", "symlink", "dangling-symlink"])
def test_pipeline_checkout_collision_fails_before_checkout(tmp_path: Path, collision: str) -> None:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
    preflight = next(step for step in steps if step["name"] == "Validate pipeline checkout destination")
    checkout = next(step for step in steps if step["name"] == "Checkout pipeline contract")
    assert steps.index(preflight) < steps.index(checkout) and preflight["if"] == checkout["if"]
    destination = tmp_path / ".pipeline-contract"
    outside = tmp_path / "outside-checkout"
    outside.mkdir()
    sentinel = outside / "caller-file"
    sentinel.write_text("preserve caller content")
    prepare = {
        "absent": lambda: None,
        "directory": destination.mkdir,
        "file": lambda: destination.write_text("existing"),
        "symlink": lambda: destination.symlink_to(outside, target_is_directory=True),
        "dangling-symlink": lambda: destination.symlink_to(tmp_path / "missing"),
    }
    prepare[collision]()
    result = subprocess.run(
        ["bash", "-c", preflight["run"]], env={**os.environ, "CONTRACT_PATH": str(destination)}, capture_output=True
    )
    assert (result.returncode == 0) == (collision == "absent")
    assert sentinel.read_text() == "preserve caller content"


@pytest.mark.parametrize(
    "profile",
    [
        "arbora",
        "connector/meristem/mcp",
        "connector/gitlab-api/mcp",
        "connector/gitlab-api/agent",
        "connector/gramps-mcp/mcp",
        "connector/gramps-mcp/agent",
        "connector/onetrust-api/mcp",
        "connector/onetrust-api/agent",
        "connector-without-graph",
    ],
)
def test_verified_context_stages_from_external_caller(tmp_path: Path, profile: str) -> None:
    case = runtime_case(
        tmp_path, ROOT, profile="connector/gitlab-api/mcp" if profile == "connector-without-graph" else profile
    )
    if profile == "connector-without-graph":
        case["manifest"]["profile"]["first_party"].pop(1)
        removed = case["manifest"]["artifacts"].pop(1)
        (case["download"] / removed["path"]).unlink()
        case["inputs"]["arbora-revision"] = ""
        lock = case["download"] / "requirements.lock"
        lock.write_text(
            lock.read_text().replace(
                f"arbora @ file:///opt/arbora-runtime/{removed['path']} \\\n    --hash=sha256:{removed['sha256']}\n", ""
            )
        )
        case["manifest"]["requirements_lock"]["sha256"] = case["inputs"]["lock-sha256"] = hashlib.sha256(
            lock.read_bytes()
        ).hexdigest()
    freeze_runtime(case)
    assert not (case["caller"] / ".github/actions").exists()
    assert (case["caller"] / ".pipeline-contract/.github/actions/stage-container-runtime/action.yml").is_file()
    prepared = run_runtime_helper(case, "prepare")
    assert prepared.returncode == 0, prepared.stderr
    result = run_runtime_helper(case)
    assert result.returncode == 0, result.stderr
    destination = case["caller"] / "build-artifacts/runtime"
    for original in case["download"].rglob("*"):
        if original.is_file():
            assert (destination / original.relative_to(case["download"])).read_bytes() == original.read_bytes()
    output = Path(case["environment"]["GITHUB_OUTPUT"]).read_text()
    for argument, key in (
        ("SOURCE_REVISION", "source-revision"),
        ("ARBORA_REVISION", "arbora-revision"),
        ("RUNTIME_LOCK_SHA256", "lock-sha256"),
        ("SOURCE_FREEZE_SHA256", "freeze-sha256"),
    ):
        assert (f"{argument}={case['inputs'][key]}\n" in output) == bool(case["inputs"][key])


def test_verified_context_accepts_branded_meristem_and_medulla_wheels(tmp_path: Path) -> None:
    case = runtime_case(tmp_path, ROOT, profile="arbora")
    manifest = case["manifest"]
    for item in manifest["profile"]["first_party"]:
        if item["distribution"] == "agent-utilities":
            item["distribution"] = "meristem"
        elif item["distribution"] == "epistemic-graph":
            item["distribution"] = "medulla"
    for item in manifest["artifacts"]:
        if item["distribution"] == "agent-utilities":
            item["distribution"] = "meristem"
        elif item["distribution"] == "epistemic-graph":
            item["distribution"] = "medulla"
    manifest["profile"]["root_requirement"] = manifest["profile"]["root_requirement"].replace(
        "agent-utilities", "meristem"
    )
    lock = case["download"] / "requirements.lock"
    lock.write_text(
        lock.read_text().replace("agent-utilities", "meristem").replace("epistemic-graph", "medulla"), encoding="utf-8"
    )
    manifest["requirements_lock"]["sha256"] = case["inputs"]["lock-sha256"] = hashlib.sha256(
        lock.read_bytes()
    ).hexdigest()
    freeze_runtime(case)
    assert run_runtime_helper(case, "prepare").returncode == 0
    result = run_runtime_helper(case)
    assert result.returncode == 0, result.stderr


def test_verified_context_accepts_old_repository_receipt_for_renamed_caller(tmp_path: Path) -> None:
    case = runtime_case(tmp_path, ROOT, profile="arbora")
    case["environment"]["CALLER_REPOSITORY"] = "Example/meristem"
    case["manifest"]["artifacts"][0]["source"]["repository"] = "Example/agent-utilities"
    case["manifest"]["profile"]["first_party"][0]["repository"] = "Example/agent-utilities"
    freeze_runtime(case)
    result = run_runtime_helper(case)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("profile", ["arbora", "connector/gitlab-api/mcp", "connector/gitlab-api/agent"])
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("artifact-id", ""),
        ("artifact-id", "1,2"),
        ("source-revision", "main"),
        ("source-revision", "a" * 40),
        ("lock-sha256", ""),
        ("freeze-sha256", "0" * 64),
        ("arbora-revision", "bad"),
        ("profile", "other"),
        ("build-context", "../escape"),
        ("build-context", "/tmp"),
        ("build-context", ".pipeline-contract"),
        ("profile", "connector/gitlab-api"),
        ("profile", "connector/gitlab-api/worker"),
        ("build-target", ""),
        ("build-target", "swap"),
        ("build-target", "wrong-final"),
    ],
)
def test_invalid_inputs_refused_before_download(tmp_path: Path, *, key: str, value: str, profile: str) -> None:
    case = runtime_case(tmp_path, ROOT, profile=profile)
    alternatives = {
        "swap": {"default": "mcp", "mcp": "agent", "agent": "mcp"},
        "wrong-final": {"default": "agent", "mcp": "default", "agent": "default"},
    }
    value = alternatives.get(value, {}).get(case["inputs"]["build-target"], value)
    freeze_runtime(case)
    case["inputs"][key] = value
    case["environment"]["RUNTIME_INPUTS"] = json.dumps(case["inputs"])
    result = run_runtime_helper(case, "prepare")
    assert result.returncode != 0
    assert not Path(case["environment"]["GITHUB_OUTPUT"]).exists()


@pytest.mark.parametrize("profile", ["arbora", "connector/gitlab-api/mcp", "connector/gitlab-api/agent"])
@pytest.mark.parametrize(
    "mutation",
    [
        "profile",
        "target",
        "source",
        "version",
        "missing-wheel",
        "duplicate-wheel",
        "missing-receipt",
        "lock-binding",
        "graph",
        "unknown-source",
        "path",
        "payload",
        "duplicate-first-party",
        "schema",
        "image-stage",
        "missing-stage",
        "missing-root",
        "root-name",
        "root-extra",
        "root-version",
        "root-marker",
        "root-range",
        "root-url",
        "root-extras-row",
        "root-extras-duplicate",
        "frozen-root-version",
        "caller-distribution",
    ],
)
def test_semantic_mismatches_refused_even_with_repinned_freeze(tmp_path: Path, mutation: str, profile: str) -> None:
    case = runtime_case(tmp_path, ROOT, profile=profile)
    manifest = case["manifest"]
    root = manifest["profile"]["first_party"][{"arbora": 1}.get(profile, 0)]
    requirement = manifest["profile"]["root_requirement"]
    changes = {
        "profile": lambda: manifest["profile"].update(name="connector/elsewhere"),
        "target": lambda: manifest["profile"]["target"].update(python="3.13"),
        "source": lambda: manifest["artifacts"][0]["source"].update(source_sha="a" * 40),
        "version": lambda: manifest["artifacts"][0].update(version="2.0"),
        "missing-wheel": lambda: manifest["artifacts"].pop(0),
        "duplicate-wheel": lambda: manifest["artifacts"].append(manifest["artifacts"][0]),
        "missing-receipt": lambda: manifest.update(verification_receipt_sha256=""),
        "lock-binding": lambda: manifest["requirements_lock"].update(sha256="a" * 64),
        "graph": lambda: case["inputs"].update({"arbora-revision": "b" * 40}),
        "unknown-source": lambda: manifest["profile"]["first_party"].pop(2),
        "path": lambda: manifest["artifacts"][0].update(path="../escape.whl"),
        "payload": lambda: manifest["artifacts"][0].update(payload_manifest_sha256=""),
        "duplicate-first-party": lambda: manifest["profile"]["first_party"].append(
            manifest["profile"]["first_party"][0]
        ),
        "schema": lambda: manifest.update(schema="arbora-runtime-wheel-inputs/1"),
        "image-stage": lambda: manifest["profile"].update(
            image_stage={"mcp": "agent"}.get(manifest["profile"]["image_stage"], "mcp")
        ),
        "missing-stage": lambda: manifest["profile"].pop("image_stage"),
        "missing-root": lambda: manifest["profile"].pop("root_requirement"),
        "root-name": lambda: manifest["profile"].update(root_requirement="other" + requirement),
        "root-extra": lambda: manifest["profile"].update(root_requirement=requirement.replace("[", "[unselected,")),
        "root-version": lambda: manifest["profile"].update(root_requirement=requirement.replace("==1.0", "==9.0")),
        "root-marker": lambda: manifest["profile"].update(root_requirement=requirement + '; python_version >= "3.14"'),
        "root-range": lambda: manifest["profile"].update(root_requirement=requirement.replace("==", ">=")),
        "root-url": lambda: manifest["profile"].update(
            root_requirement=requirement.replace("==1.0", " @ https://example.invalid/root.whl")
        ),
        "root-extras-row": lambda: root.update(extras=[]),
        "root-extras-duplicate": lambda: root["extras"].append(root["extras"][0]),
        "frozen-root-version": lambda: root.update(version="1.*"),
        "caller-distribution": lambda: manifest["profile"]["first_party"][0].update(distribution="other"),
    }
    changes[mutation]()
    freeze_runtime(case)
    result = run_runtime_helper(case)
    assert result.returncode != 0, mutation
    assert not (case["caller"] / "build-artifacts/runtime").exists()


@pytest.mark.parametrize(
    "mutation",
    ["freeze", "lock", "wheel", "extra", "symlink", "context-link", "overlay", "source-checkout", "pipeline-checkout"],
)
def test_changed_bytes_or_unsafe_staging_never_overwrites_caller(tmp_path: Path, mutation: str) -> None:
    case = runtime_case(tmp_path, ROOT)
    freeze_runtime(case)
    destination = case["caller"] / "build-artifacts/runtime"
    wheel = case["download"] / case["manifest"]["artifacts"][0]["path"]
    changes = {
        "freeze": lambda: (case["download"] / "source-freeze.json").write_text("{}"),
        "lock": lambda: (case["download"] / "requirements.lock").write_text("altered"),
        "wheel": lambda: wheel.write_bytes(b"altered"),
        "extra": lambda: (case["download"] / "unlisted.whl").write_text("extra"),
        "symlink": lambda: (case["download"] / "link").symlink_to(wheel),
        "context-link": lambda: (case["caller"] / "build-artifacts").symlink_to(
            case["download"], target_is_directory=True
        ),
        "overlay": lambda: destination.mkdir(parents=True),
        "source-checkout": lambda: case["environment"].update(EXPECTED_SOURCE="b" * 40),
        "pipeline-checkout": lambda: case["environment"].update(EXPECTED_PIPELINE="b" * 40),
    }
    changes[mutation]()
    result = run_runtime_helper(case)
    assert result.returncode != 0, mutation
    assert not (destination / "source-freeze.json").exists()


@pytest.mark.parametrize(
    "replacement",
    [
        "--index-url https://example.invalid/simple",
        "-e .",
        "name>=1",
        "agent-utilities==1.0 --hash=sha256:{hash}",
        "agent-utilities @ https://example.invalid/package.whl --hash=sha256:{hash}",
        "agent-utilities[unselected] @ file:///opt/arbora-runtime/{path} --hash=sha256:{hash}",
        "agent-utilities @ file:///opt/arbora-runtime/{path} --hash=sha256:" + "b" * 64,
    ],
)
def test_lock_cannot_reintroduce_resolution_or_unselected_extras(tmp_path: Path, replacement: str) -> None:
    case = runtime_case(tmp_path, ROOT)
    item = case["manifest"]["artifacts"][0]
    lock = case["download"] / "requirements.lock"
    lines = lock.read_text().splitlines()
    lock.write_text(replacement.format(hash=item["sha256"], path=item["path"]) + "\n" + "\n".join(lines[2:]) + "\n")
    case["inputs"]["lock-sha256"] = case["manifest"]["requirements_lock"]["sha256"] = hashlib.sha256(
        lock.read_bytes()
    ).hexdigest()
    freeze_runtime(case)
    result = run_runtime_helper(case)
    assert result.returncode != 0
    assert not (case["caller"] / "build-artifacts/runtime").exists()


def _version_step() -> dict:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
    return next(step for step in steps if step.get("id") == "version")


@pytest.mark.parametrize(
    ("files", "context", "expected"),
    [
        ({"pyproject.toml": '[project]\nname = "x"\nversion = "2.2.0"\n'}, ".", "2.2.0"),
        ({"pyproject.toml": "[project]\r\nversion = '1.0.0rc1'  # pinned\r\n"}, ".", "1.0.0rc1"),
        ({"pyproject.toml": '[tool.x]\nversion = "9.9.9"\n[project]\nversion = "3.1.4"\n'}, ".", "3.1.4"),
        ({"pyproject.toml": '[project]\ndynamic = ["version"]\n'}, ".", ""),
        (
            {
                "pyproject.toml": '[project]\ndynamic = ["version"]\n[tool.setuptools.dynamic]\n'
                'version = {attr = "pkg._version.__version__"}\n',
                "pkg/_version.py": '"""v."""\n__version__ = "2.3.1"\n',
            },
            ".",
            "2.3.1",
        ),
        (
            {
                "pyproject.toml": '[project]\ndynamic = ["version"]\n[tool.setuptools.dynamic]\n'
                "version = { attr = 'pkg.__version__' }\n",
                "src/pkg/__init__.py": "__version__ = '0.9.0'\n",
            },
            ".",
            "",
        ),
        (
            {
                "pyproject.toml": '[project]\ndynamic = ["version"]\n[tool.setuptools.dynamic]\n'
                'version = {attr = "pkg.__version__"}\n',
                "src/pkg/__init__.py": "__version__ = '0.9.0'\n",
            },
            ".",
            "0.9.0",
        ),
        (
            {
                "pyproject.toml": '[project]\ndynamic = ["version"]\n[tool.setuptools.dynamic]\n'
                'version = {attr = "pkg.__version__"}\n',
                "pkg/__init__.py": '__version__ = "1.0 ;touch x"\n',
            },
            ".",
            None,
        ),
        ({"Cargo.toml": '[package]\nname = "x"\nversion = "0.4.2"\n[dependencies]\n'}, ".", "0.4.2"),
        (
            {
                "pkg/pyproject.toml": '[project]\nversion = "5.0.0"\n',
                "pyproject.toml": '[project]\nversion = "1.0.0"\n',
            },
            "pkg",
            "5.0.0",
        ),
        ({"pyproject.toml": '[project]\nversion = "v1.2.3+local.1"\n'}, ".", "1.2.3-local.1"),
        ({}, ".", ""),
        ({"pyproject.toml": '[project]\nversion = "1.0 ;touch x"\n'}, ".", None),
    ],
)
def test_version_tag_source(tmp_path: Path, *, files: dict[str, str], context: str, expected: str | None) -> None:
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(text.encode())
    output = tmp_path / "output"
    environment = {**os.environ, "GITHUB_OUTPUT": str(output), "BUILD_CONTEXT": context}
    result = subprocess.run(["bash", "-c", _version_step()["run"]], env=environment, cwd=tmp_path, capture_output=True)
    if expected is None:
        assert result.returncode != 0
        return
    assert result.returncode == 0, result.stderr
    assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == {"version": expected}


def test_version_tags_keep_existing_tags_and_publish_from_main_only() -> None:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"]
    meta = next(step for step in steps if step.get("id") == "meta")
    assert steps.index(_version_step()) < steps.index(meta)
    assert _version_step()["if"] == "steps.target.outputs.exists == 'true'"
    on_main = "(github.event_name == 'push' && github.ref == 'refs/heads/main') || inputs.release_repair == true"
    on_main_version = f"({on_main}) && steps.version.outputs.version != ''"
    assert meta["with"]["tags"].splitlines() == [
        "type=ref,event=branch,suffix=${{ matrix.suffix }}",
        "type=ref,event=pr,suffix=${{ matrix.suffix }}",
        "type=sha,suffix=${{ matrix.suffix }}",
        f"type=raw,value=${{{{ matrix.main_tag }}}},enable=${{{{ {on_main} }}}}",
        "type=raw,value=${{ steps.version.outputs.version }},suffix=${{ matrix.suffix }},"
        f"enable=${{{{ {on_main_version} }}}}",
        "type=raw,value=${{ steps.version.outputs.version }}-sdk${{ inputs.sdk_version }}${{ matrix.suffix }},"
        "enable=${{ inputs.sdk_version != '' && steps.version.outputs.version != '' && inputs.sdk_distribution != 'scion-sdk' }}",
        "type=raw,value=${{ steps.version.outputs.version }}-sdk-${{ inputs.sdk_distribution }}-${{ inputs.sdk_version }}${{ matrix.suffix }},"
        "enable=${{ inputs.sdk_version != '' && steps.version.outputs.version != '' && inputs.sdk_distribution == 'scion-sdk' }}",
    ]


def test_release_builds_use_one_persistent_builder() -> None:
    # spec: PIPE-RELEASE-R015
    text = WORKFLOW.read_text()
    assert "docker/setup-buildx-action" not in text
    assert "buildx rm --force" in text  # a wedged builder is replaced, never a healthy one removed per job
    steps = yaml.safe_load(text)["jobs"]["publish-docker"]["steps"]
    builder = next(step for step in steps if step.get("id") == "builder")
    assert 'buildx create --name "$BUILDER_NAME"' in builder["run"]
    assert 'buildx inspect "$BUILDER_NAME" > /dev/null' in builder["run"]
    assert "timeout 300" in builder["run"]
    builds = [step for step in steps if "docker/build-push-action@" in step.get("uses", "")]
    assert len(builds) == 3
    assert all(build["with"]["builder"] == "${{ steps.builder.outputs.name }}" for build in builds)
    assert steps.index(builder) < steps.index(builds[0])
    cache = builds[0]["with"]
    assert cache["cache-from"].endswith(":buildcache-${{ steps.target.outputs.cache-key }}")
    assert "mode=max" in cache["cache-to"]
    assert "ignore-error=true" in cache["cache-to"]
    prune = next(step for step in steps if step["name"] == "Bound the builder cache")
    assert "--keep-storage" in prune["run"] and prune["if"].startswith("always()")
