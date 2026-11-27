"""Focused contracts for the reusable Python release action."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import yaml


ACTION = Path(__file__).parents[1] / ".github/actions/publish-python-package/action.yml"
RELEASE_ACTION = Path(__file__).parents[1] / ".github/actions/create-version-release/action.yml"
WORKFLOW = Path(__file__).parents[1] / ".github/workflows/python_pipeline.yml"
ROOT = Path(__file__).parents[1]


def test_release_body_has_an_unambiguous_commit_identity() -> None:
    text = ACTION.read_text(encoding="utf-8")

    assert "uv pip install --require-hashes -r" in text
    assert "twine-requirements.txt" in text
    assert ".venv/bin/twine upload" in text
    assert "./.pipeline-contract/.github/actions/verify-source-commit" in text
    assert 'LATEST_COMMIT="$SOURCE_COMMIT"' in text
    assert 'COMMIT_MESSAGE=$(git log -1 --format=%B "$LATEST_COMMIT"' in text
    assert 'echo "LATEST_COMMIT=$LATEST_COMMIT"' in text
    assert "Commit: ${{ env.LATEST_COMMIT }}" in RELEASE_ACTION.read_text(encoding="utf-8")
    assert "Pipelines contract: ${{ env.PIPELINES_CONTRACT_COMMIT }}" in RELEASE_ACTION.read_text(encoding="utf-8")


def test_release_metadata_does_not_depend_on_an_undefined_tag_variable() -> None:
    text = ACTION.read_text(encoding="utf-8")

    assert "if [[ $TAG" not in text
    assert "CURRENT_COMMIT" not in text
    assert "CURRENT_RELEASE" not in text
    assert "COMMIT_DIFFERENCE" not in text


def test_python_workflow_bootstraps_contract_before_external_local_action() -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["publish-pypi"]["steps"]
    contract = next(step for step in steps if step.get("name") == "Checkout pipeline contract")
    publisher = next(step for step in steps if step.get("name") == "Build, publish and release")
    trigger = document.get("on", document.get(True))
    role_contract = trigger["workflow_call"]["inputs"]["role-contract"]

    assert contract["uses"].startswith("actions/checkout@")
    assert contract["with"] == {
        "repository": "${{ job.workflow_repository }}",
        "ref": "${{ job.workflow_sha }}",
        "sparse-checkout": (
            "/.github/actions/\n"
            "/pipelines_hooks/__init__.py\n"
            "/pipelines_hooks/connector/__init__.py\n"
            "/pipelines_hooks/connector/project.py\n"
            "/pipelines_hooks/connector/targets.py\n"
            "/pipelines_hooks/core/__init__.py\n"
            "/pipelines_hooks/core/errors.py\n"
            "/scripts/release_record.py\n"
            "/scripts/release_sign_plan.py\n"
            "/reference/connector-release.lock\n"
        ),
        "sparse-checkout-cone-mode": False,
        "path": ".pipeline-contract",
        "persist-credentials": False,
    }
    assert publisher["uses"] == "./.pipeline-contract/.github/actions/publish-python-package"
    assert role_contract["required"] is False
    assert role_contract["default"] == ""
    assert role_contract["type"] == "string"
    assert publisher["with"]["role-contract"] == "${{ inputs.role-contract }}"


def test_python_workflow_sparse_contract_keeps_readiness_validator_importable(tmp_path: Path) -> None:
    """The hosted sparse checkout contains the canonical readiness import closure."""

    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    checkout = next(
        step for step in document["jobs"]["publish-pypi"]["steps"] if step.get("name") == "Checkout pipeline contract"
    )
    sparse = checkout["with"]["sparse-checkout"].splitlines()
    closure = (
        ".github/actions/wheel-readiness/readiness.py",
        "pipelines_hooks/__init__.py",
        "pipelines_hooks/connector/__init__.py",
        "pipelines_hooks/connector/project.py",
        "pipelines_hooks/connector/targets.py",
        "pipelines_hooks/core/__init__.py",
        "pipelines_hooks/core/errors.py",
    )

    assert checkout["with"]["sparse-checkout-cone-mode"] is False
    assert "/.github/actions/" in sparse
    assert all(f"/{path}" in sparse for path in closure[1:])

    caller = tmp_path / "caller"
    contract = caller / ".pipeline-contract"
    for relative in closure:
        source = ROOT / relative
        destination = contract / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (caller / "pyproject.toml").write_text(
        '[tool.pipelines]\nallow-source-build = ["Uptime_Kuma.API"]\n', encoding="utf-8"
    )
    probe = textwrap.dedent(
        """
        import importlib.util
        from pathlib import Path

        script = Path('.pipeline-contract/.github/actions/wheel-readiness/readiness.py')
        spec = importlib.util.spec_from_file_location('readiness_probe', script)
        assert spec is not None and spec.loader is not None
        readiness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(readiness)
        print(readiness.source_build_allowance(Path.cwd()))
        """
    )
    environment = {**os.environ, "PYTHONPATH": ""}
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        cwd=caller,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['uptime-kuma-api']"


def test_publish_action_persists_uv_cache_in_tool_cache() -> None:
    # spec: PIPE-RELEASE-R016
    steps = yaml.safe_load(ACTION.read_text(encoding="utf-8"))["runs"]["steps"]
    cache = next(step for step in steps if step["name"] == "Persist uv downloads across runs")
    assert steps.index(cache) == 0  # before any step that runs uv
    assert 'echo "UV_CACHE_DIR=$root/uv-cache"' in cache["run"]
    assert 'echo "UV_PYTHON_INSTALL_DIR=$root/uv-python"' in cache["run"]
    assert "RUNNER_TOOL_CACHE" in cache["run"]


def _sign_step_run(
    tmp_path: Path, key: str, key_id: str, exit_code: int
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the signing step's script against a stub ``uvx`` inside a minimal connector checkout."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    sign = next(
        step for step in document["jobs"]["publish-pypi"]["steps"] if step.get("name") == "Sign the live declaration"
    )
    work = tmp_path / f"work{exit_code}{bool(key)}{bool(key_id)}"
    (work / "demo_connector").mkdir(parents=True)
    (work / "pyproject.toml").write_text(
        '[project]\nname = "demo-connector"\n[project.scripts]\ndemo-connector = "demo_connector.mcp_server:mcp_server"\n'
        '[tool.pipelines_hooks]\npackages = ["demo_connector"]\n',
        encoding="utf-8",
    )
    (work / ".pipeline-contract").symlink_to(ROOT)
    bin_dir = work / "bin"
    bin_dir.mkdir()
    for tool in ("uv", "uvx"):
        stub = bin_dir / tool
        stub.write_text(f'#!/bin/sh\nfor a in "$@"; do echo "$a"; done > "{bin_dir}/{tool}.args"\nexit {exit_code}\n')
        stub.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RELEASE_SIGNING_KEY": key,
        "RELEASE_SIGNING_KEY_ID": key_id,
    }
    done = subprocess.run(["bash", "-c", sign["run"]], env=env, cwd=work, capture_output=True, text=True, check=False)
    return done, bin_dir / "uvx.args"


def test_connector_release_signs_before_the_wheel_build(tmp_path: Path) -> None:
    # spec: PIPE-RELEASE-R019
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["publish-pypi"]["steps"]
    names = [step.get("name") for step in steps]
    sign = steps[names.index("Sign the live declaration")]
    assert names.index("Generate the connector ontology artifacts") < names.index("Sign the live declaration")
    assert names.index("Verify release version") < names.index("Sign the live declaration")
    assert names.index("Sign the live declaration") < names.index("Build, publish and release")
    assert sign["if"] == "steps.version.outputs.published != 'true' && inputs.connector"
    inputs = (document.get("on", document.get(True)))["workflow_call"]["inputs"]
    assert inputs["release-signing-key"]["default"] == ""
    assert inputs["release-signing-key-id"]["default"] == ""
    assert sign["env"] == {
        "RELEASE_SIGNING_KEY": "${{ inputs.release-signing-key }}",
        "RELEASE_SIGNING_KEY_ID": "${{ inputs.release-signing-key-id }}",
    }

    ref = "openbao://apps/release-signing/connectors#SIGNING_KEY@1"
    signed, args_file = _sign_step_run(tmp_path, ref, "release-key", 0)
    assert signed.returncode == 0, signed.stderr
    assert args_file.read_text().split("\n")[:-1] == [
        "--from",
        "scion-sdk[mcp]>=0.12.1",
        "connector-release-sign",
        "--package-root",
        "demo_connector",
        "--connector",
        "release-signing",
        "--key-id",
        "release-key",
        "--key-ref",
        ref,
        "--lock",
        ".pipeline-contract/reference/connector-release.lock",
        "--",
        "uv",
        "run",
        "--frozen",
        "demo-connector",
    ]  # every argument the signing command requires, then the connector's stdio command

    assert _sign_step_run(tmp_path, ref, "release-key", 2)[0].returncode != 0  # a failed signing fails the release
    for key, key_id in (("", "release-key"), (ref, "")):  # unsigned: refused before the wheel is built
        unsigned = _sign_step_run(tmp_path, key, key_id, 0)[0]
        assert unsigned.returncode != 0 and "must be signed" in unsigned.stdout


def test_release_key_lock_pins_the_signer_the_org_variable_names() -> None:
    # spec: PIPE-RELEASE-R019
    lock = yaml.safe_load((ROOT / "reference/connector-release.lock").read_text(encoding="utf-8"))
    pins = {entry["signer"]: entry["signing_public_key"] for entry in lock.values()}
    assert len(lock) == 1 and set(pins) == {"knuckles-connector-release-2026"}
    assert len(pins["knuckles-connector-release-2026"]) == 43  # an unpadded base64url Ed25519 public key
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "/reference/connector-release.lock" in text and "/scripts/release_sign_plan.py" in text  # sparse-checked out
