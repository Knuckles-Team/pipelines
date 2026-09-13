"""Focused contracts for the reusable Python release action."""

from __future__ import annotations

from pathlib import Path

import yaml


ACTION = Path(__file__).parents[1] / ".github/actions/publish-python-package/action.yml"
RELEASE_ACTION = Path(__file__).parents[1] / ".github/actions/create-version-release/action.yml"
WORKFLOW = Path(__file__).parents[1] / ".github/workflows/python_pipeline.yml"


def test_release_body_has_an_unambiguous_commit_identity() -> None:
    text = ACTION.read_text(encoding="utf-8")

    assert "uv pip install --require-hashes -r" in text
    assert "twine-requirements.txt" in text
    assert '.venv/bin/twine upload' in text
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

    assert contract["uses"].startswith("actions/checkout@")
    assert contract["with"] == {
        "repository": "${{ job.workflow_repository }}",
        "ref": "${{ job.workflow_sha }}",
        "path": ".pipeline-contract",
        "persist-credentials": False,
    }
    assert publisher["uses"] == "./.pipeline-contract/.github/actions/publish-python-package"
