"""Contracts for the desktop reusable workflow's external action bootstrap."""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.workflow_fixtures import external_caller


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/desktop_release_pipeline.yml"
SETUP_ACTION = ROOT / ".github/actions/setup-python-uv/action.yml"


def test_desktop_workflow_bootstraps_contract_for_an_external_caller(tmp_path: Path) -> None:
    caller = external_caller(
        tmp_path,
        ROOT,
        "external-desktop-caller",
        """name: External desktop release\n\non:\n  push:\n    tags: ['v*']\n\njobs:\n  release:\n    uses: Knuckles-Team/pipelines/.github/workflows/desktop_release_pipeline.yml@main\n    secrets: inherit\n""",
    )
    assert not (caller / ".github/actions").exists()

    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for name in ("build-linux", "build-windows"):
        steps = document["jobs"][name]["steps"]
        contract = steps[0]
        setup = steps[1]
        assert contract["uses"].startswith("actions/checkout@")
        assert contract["with"]["repository"] == "${{ job.workflow_repository }}"
        assert contract["with"]["ref"] == "${{ job.workflow_sha }}"
        assert contract["with"]["path"] == ".pipeline-contract"
        assert setup["uses"] == "./.pipeline-contract/.github/actions/setup-python-uv"
        assert (caller / setup["uses"][2:]).exists()

        for step in steps:
            action = step.get("uses", "")
            if action.startswith("./"):
                assert action.startswith("./.pipeline-contract/")
                assert (caller / action[2:]).exists()


def test_desktop_setup_binds_caller_and_contract_commits() -> None:
    text = SETUP_ACTION.read_text(encoding="utf-8")

    assert "./.pipeline-contract/.github/actions/checkout-verified-source" in text


def test_windows_installer_compiles_the_packaging_script() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '"/DMyAppVersion=$VERSION" packaging\\windows\\setup.iss' in text
    assert " setup.iss" not in text.replace("packaging\\windows\\setup.iss", "")
