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


def test_connector_release_pins_digests_before_publication_and_holds_no_key() -> None:
    # spec: PIPE-RELEASE-R019
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    inputs = (document.get("on", document.get(True)))["workflow_call"]["inputs"]
    assert not [name for name in inputs if "signing" in name]
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "connector-release-sign" not in text and "release_sign_plan" not in text
    assert "connector-release.lock" not in text
    step = next(
        step for step in document["jobs"]["publish-pypi"]["steps"] if step.get("name") == "Build, publish and release"
    )
    assert step["with"]["release-digests"] == "${{ inputs.connector && 'release-digests.json' || '' }}"
    steps = document["jobs"]["publish-pypi"]["steps"]
    assert "Record the release" not in [s.get("name") for s in steps]
    assert "release-record-url" not in inputs and "release_record" not in text
    assert not (ROOT / "scripts/release_record.py").exists()
    action = yaml.safe_load((ROOT / ".github/actions/publish-python-package/action.yml").read_text(encoding="utf-8"))
    names = [s.get("name") for s in action["runs"]["steps"]]
    compute = action["runs"]["steps"][names.index("Compute the release digests")]
    assert names.index("Compute the release digests") < names.index("Publish package")
    assert compute["if"] == "inputs.release-digests != ''"
    assert "connector-release-digest" in compute["run"] and "--sdist" in compute["run"]
    assert "GITHUB_STEP_SUMMARY" in compute["run"]
    caller = (ROOT / ".github/workflows/connector_pipeline.yml").read_text(encoding="utf-8")
    assert "RELEASE_SIGNING_KEY" not in caller and "release-signing" not in caller
    assert not (ROOT / "reference/connector-release.lock").exists()
    assert not (ROOT / "scripts/release_sign_plan.py").exists()
