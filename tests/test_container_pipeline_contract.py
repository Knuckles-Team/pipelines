"""Container callers retain legacy targets; opted-in bytes fail closed before build."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.workflow_fixtures import freeze_runtime, runtime_case

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/container_pipeline.yml"
ACTION = ROOT / ".github/actions/stage-container-runtime/action.yml"
SCRIPT = ROOT / ".github/actions/stage-container-runtime/stage_runtime.py"


def run_helper(case: dict, phase: str = "stage") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(SCRIPT), phase], cwd=case["caller"],
                          env=case["environment"], text=True, capture_output=True)


def test_workflow_contract_and_legacy_publication_controls() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    job = workflow["jobs"]["publish-docker"]
    steps = job["steps"]
    checkout = next(step for step in steps if step["name"] == "Checkout pipeline contract")
    assert checkout["with"]["repository"] == "${{ job.workflow_repository }}"
    assert checkout["with"]["ref"] == "${{ job.workflow_sha }}"
    assert checkout["if"] == "steps.target.outputs.exists == 'true' && steps.target.outputs.runtime == 'true'"
    assert next(step for step in steps if step.get("id") == "runtime")["if"] == checkout["if"]
    assert workflow["permissions"] == {"contents": "read"}
    assert job["runs-on"] == "self-hosted"
    assert job["strategy"]["matrix"]["include"] == [
        {"target": "agent", "suffix": "", "main_tag": "latest"},
        {"target": "mcp", "suffix": "-mcp", "main_tag": "mcp"}]
    builds = [step for step in steps if "docker/build-push-action@" in step.get("uses", "")]
    assert len(builds) == 3 and builds[0]["with"] == builds[1]["with"] == builds[2]["with"]
    assert builds[0]["with"]["build-args"] == "${{ steps.runtime.outputs.build-args }}"
    assert builds[0]["with"]["target"] == "${{ steps.target.outputs.target }}"
    assert builds[0]["with"]["push"] == "${{ github.event_name == 'push' }}"
    assert steps.index(next(step for step in steps if step.get("id") == "runtime")) < steps.index(builds[0])


@pytest.mark.parametrize(("requested", "leg", "dockerfile", "expected"), [
    ("", "agent", "FROM base AS agent\n", (True, "agent", False)),
    ("", "mcp", "FROM base AS agent\n", (False, None, False)),
    ("", "mcp", "from base as mcp\n", (True, "mcp", False)),
    ("default", "agent", "FROM base\n", (True, "", False)),
    ("default", "mcp", "FROM base\n", (False, None, False)),
    ("runtime", "agent", "FROM base AS runtime\n", (True, "runtime", False)),
    ("mcp", "mcp", "FROM base AS mcp\n", (True, "mcp", False)),
    ("mcp", "agent", "FROM base AS mcp\n", (False, None, False)),
    ("missing", "agent", "FROM base\n", (False, None, True)),
    ("bad;touch injected", "agent", "FROM base\n", (False, None, True)),
])
def test_target_selection(tmp_path: Path, *, requested: str, leg: str, dockerfile: str,
                          expected: tuple[bool, str | None, bool]) -> None:
    enabled, target, fails = expected
    step = next(step for step in yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"] if step.get("id") == "target")
    recipe = tmp_path / "Dockerfile"
    recipe.write_text(dockerfile)
    output = tmp_path / "output"
    environment = {**os.environ, "DOCKERFILE": str(recipe), "GITHUB_OUTPUT": str(output),
                   "REQUESTED_TARGET": requested, "MATRIX_TARGET": leg, "RUNTIME_REQUEST": ""}
    result = subprocess.run(["bash", "-c", step["run"]], env=environment, capture_output=True)
    assert (result.returncode != 0) == fails
    if not fails:
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        assert values["exists"] == str(enabled).lower()
        assert values.get("target") == target
        assert values["runtime"] == "false"


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
    step = next(step for step in yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-docker"]["steps"] if step.get("id") == "target")
    environment = {**os.environ, "DOCKERFILE": "absent", "GITHUB_OUTPUT": str(tmp_path / "output"),
                   "REQUESTED_TARGET": "", "MATRIX_TARGET": "agent", "RUNTIME_REQUEST": "1234"}
    result = subprocess.run(["bash", "-c", step["run"]], env=environment, capture_output=True)
    assert result.returncode != 0
    assert (tmp_path / "output").read_text() == "runtime=true\n"


@pytest.mark.parametrize("profile", ["graphos", "connector/agent-utilities", "connector-without-graph"])
def test_verified_context_stages_from_external_caller(tmp_path: Path, profile: str) -> None:
    case = runtime_case(tmp_path, ROOT)
    if profile == "connector-without-graph":
        case["manifest"]["profile"]["first_party"].pop(1)
        removed = case["manifest"]["artifacts"].pop(1)
        (case["download"] / removed["path"]).unlink()
        case["inputs"]["graph-os-revision"] = ""
        lock = case["download"] / "requirements.lock"
        lock.write_text(lock.read_text().replace(f"graph-os @ file:///opt/graphos-runtime/{removed['path']} \\\n    --hash=sha256:{removed['sha256']}\n", ""))
        profile = "connector/agent-utilities"
    if profile.startswith("connector/"):
        case["manifest"]["profile"]["name"] = case["inputs"]["profile"] = profile
        case["manifest"]["profile"]["first_party"][0]["extras"] = ["mcp"]
        lock = case["download"] / "requirements.lock"
        lock.write_text(lock.read_text().replace("agent-utilities @", "agent-utilities[mcp] @"))
        case["manifest"]["requirements_lock"]["sha256"] = case["inputs"]["lock-sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
    freeze_runtime(case)
    assert not (case["caller"] / ".github/actions").exists()
    assert (case["caller"] / ".pipeline-contract/.github/actions/stage-container-runtime/action.yml").is_file()
    prepared = run_helper(case, "prepare")
    assert prepared.returncode == 0, prepared.stderr
    result = run_helper(case)
    assert result.returncode == 0, result.stderr
    destination = case["caller"] / "build-artifacts/runtime"
    for original in case["download"].rglob("*"):
        if original.is_file():
            assert (destination / original.relative_to(case["download"])).read_bytes() == original.read_bytes()
    output = Path(case["environment"]["GITHUB_OUTPUT"]).read_text()
    for argument, key in (("SOURCE_REVISION", "source-revision"), ("GRAPH_OS_REVISION", "graph-os-revision"),
                          ("RUNTIME_LOCK_SHA256", "lock-sha256"), ("SOURCE_FREEZE_SHA256", "freeze-sha256")):
        assert (f"{argument}={case['inputs'][key]}\n" in output) == bool(case["inputs"][key])


@pytest.mark.parametrize(("key", "value"), [("artifact-id", ""), ("artifact-id", "1,2"),
    ("source-revision", "main"), ("source-revision", "a" * 40), ("lock-sha256", ""),
    ("freeze-sha256", "0" * 64), ("graph-os-revision", "bad"), ("profile", "other"),
    ("build-context", "../escape"), ("build-context", "/tmp"), ("build-context", ".pipeline-contract")])
def test_invalid_inputs_refused_before_download(tmp_path: Path, key: str, value: str) -> None:
    case = runtime_case(tmp_path, ROOT)
    freeze_runtime(case)
    case["inputs"][key] = value
    case["environment"]["RUNTIME_INPUTS"] = json.dumps(case["inputs"])
    result = run_helper(case, "prepare")
    assert result.returncode != 0
    assert not Path(case["environment"]["GITHUB_OUTPUT"]).exists()


@pytest.mark.parametrize("mutation", ["profile", "target", "source", "version", "missing-wheel", "duplicate-wheel",
    "missing-receipt", "lock-binding", "graph", "unknown-source", "path", "payload", "duplicate-first-party"])
def test_semantic_mismatches_refused_even_with_repinned_freeze(tmp_path: Path, mutation: str) -> None:
    case = runtime_case(tmp_path, ROOT)
    manifest = case["manifest"]
    changes = {
        "profile": lambda: manifest["profile"].update(name="connector/elsewhere"),
        "target": lambda: manifest["profile"]["target"].update(python="3.13"),
        "source": lambda: manifest["artifacts"][0]["source"].update(source_sha="a" * 40),
        "version": lambda: manifest["artifacts"][0].update(version="2.0"),
        "missing-wheel": lambda: manifest["artifacts"].pop(0),
        "duplicate-wheel": lambda: manifest["artifacts"].append(manifest["artifacts"][0]),
        "missing-receipt": lambda: manifest.update(verification_receipt_sha256=""),
        "lock-binding": lambda: manifest["requirements_lock"].update(sha256="a" * 64),
        "graph": lambda: case["inputs"].update({"graph-os-revision": "b" * 40}),
        "unknown-source": lambda: manifest["profile"]["first_party"].pop(2),
        "path": lambda: manifest["artifacts"][0].update(path="../escape.whl"),
        "payload": lambda: manifest["artifacts"][0].update(payload_manifest_sha256=""),
        "duplicate-first-party": lambda: manifest["profile"]["first_party"].append(manifest["profile"]["first_party"][0]),
    }
    changes[mutation]()
    freeze_runtime(case)
    result = run_helper(case)
    assert result.returncode != 0, mutation
    assert not (case["caller"] / "build-artifacts/runtime").exists()


@pytest.mark.parametrize("mutation", ["freeze", "lock", "wheel", "extra", "symlink", "context-link", "overlay", "source-checkout", "pipeline-checkout"])
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
        "context-link": lambda: (case["caller"] / "build-artifacts").symlink_to(case["download"], target_is_directory=True),
        "overlay": lambda: destination.mkdir(parents=True),
        "source-checkout": lambda: case["environment"].update(EXPECTED_SOURCE="b" * 40),
        "pipeline-checkout": lambda: case["environment"].update(EXPECTED_PIPELINE="b" * 40),
    }
    changes[mutation]()
    result = run_helper(case)
    assert result.returncode != 0, mutation
    assert not (destination / "source-freeze.json").exists()


@pytest.mark.parametrize("replacement", ["--index-url https://example.invalid/simple", "-e .", "name>=1",
    "agent-utilities==1.0 --hash=sha256:{hash}",
    "agent-utilities @ https://example.invalid/package.whl --hash=sha256:{hash}",
    "agent-utilities[unselected] @ file:///opt/graphos-runtime/{path} --hash=sha256:{hash}",
    "agent-utilities @ file:///opt/graphos-runtime/{path} --hash=sha256:" + "b" * 64])
def test_lock_cannot_reintroduce_resolution_or_unselected_extras(tmp_path: Path, replacement: str) -> None:
    case = runtime_case(tmp_path, ROOT)
    item = case["manifest"]["artifacts"][0]
    lock = case["download"] / "requirements.lock"
    lines = lock.read_text().splitlines()
    lock.write_text(replacement.format(hash=item["sha256"], path=item["path"]) + "\n" + "\n".join(lines[2:]) + "\n")
    case["inputs"]["lock-sha256"] = case["manifest"]["requirements_lock"]["sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
    freeze_runtime(case)
    result = run_helper(case)
    assert result.returncode != 0
    assert not (case["caller"] / "build-artifacts/runtime").exists()
