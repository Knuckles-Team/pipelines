"""PIPE-RELEASE-R033: the shared npm lane declares its inputs and publishes only on a v* tag."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/npm_pipeline.yml"
STRING_INPUTS = {"node-version", "package-manager", "typecheck", "lint", "test", "build", "pre-publish"}


def _load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_the_lane_declares_its_inputs_and_publishes_only_on_a_tag() -> None:
    # spec: PIPE-RELEASE-R033
    document = _load()
    call = document[True]["workflow_call"]  # PyYAML reads the key `on` as True
    inputs = call["inputs"]
    assert set(inputs) == STRING_INPUTS | {"publish"}
    assert all(inputs[name]["type"] == "string" for name in STRING_INPUTS)
    assert inputs["publish"]["type"] == "boolean" and inputs["publish"]["default"] is False
    assert inputs["node-version"]["default"] == "22" and inputs["package-manager"]["default"] == "pnpm"
    assert call["secrets"]["NPM_TOKEN"]["required"] is False

    steps = {step["name"]: step for step in document["jobs"]["npm"]["steps"]}
    for name in ("Verify the tag version", "Pre-publish", "Detect the publish mode"):
        condition = steps[name]["if"]
        assert "inputs.publish" in condition and "refs/tags/v" in condition, name
    assert "npm publish --provenance --access public" in steps["Publish by trusted publishing"]["run"]
    assert "pipelines-hook npm-tag-version" in steps["Verify the tag version"]["run"]
    for gate in ("Typecheck", "Lint", "Test", "Build"):
        assert "GATE_FAILED" in steps[gate]["run"], gate
    order = list(steps)
    assert (
        order.index("Build")
        < order.index("Verify the tag version")
        < order.index("Pre-publish")
        < order.index("Detect the publish mode")
        < order.index("Publish the first release with the token")
        < order.index("Register the trusted publisher")
        < order.index("Publish by trusted publishing")
    )
    assert document["jobs"]["npm"]["permissions"]["id-token"] == "write"


def _steps() -> dict[str, dict]:
    return {step["name"]: step for step in _load()["jobs"]["npm"]["steps"]}


def test_every_publish_carries_provenance() -> None:
    # spec: PIPE-RELEASE-R033.1
    steps = _steps()
    for name in ("Publish the first release with the token", "Publish by trusted publishing"):
        assert "npm publish --provenance --access public" in steps[name]["run"], name


def test_the_token_reaches_only_the_first_publish_step() -> None:
    # spec: PIPE-RELEASE-R033.2
    steps = _steps()
    assert steps["Detect the publish mode"]["env"]["NODE_AUTH_TOKEN"] == ""
    assert "E404" in steps["Detect the publish mode"]["run"] and "npm view" in steps["Detect the publish mode"]["run"]
    first = steps["Publish the first release with the token"]
    assert first["if"] == "steps.mode.outputs.mode == 'first'"
    assert first["env"]["NODE_AUTH_TOKEN"] == "${{ secrets.NPM_TOKEN }}"
    assert "NPM_AUTH_MISSING" in first["run"]
    holders = [n for n, step in steps.items() if "NPM_TOKEN" in str(step.get("env", {}))]
    assert holders == ["Publish the first release with the token", "Register the trusted publisher"]


def test_the_lane_registers_the_trusted_publisher_after_the_first_publish_and_warns_when_refused() -> None:
    # spec: PIPE-RELEASE-R033.3
    step = _steps()["Register the trusted publisher"]
    assert step["if"] == "steps.mode.outputs.mode == 'first'"
    assert "npm trust github" in step["run"] and "--file" in step["run"] and "--yes" in step["run"]
    assert "TRUSTED_PUBLISHER_UNREGISTERED" in step["run"] and "exit 1" not in step["run"]
    assert "^11.10.0" in _steps()["Detect the publish mode"]["run"]


def test_a_known_package_publishes_by_oidc_with_an_empty_token() -> None:
    # spec: PIPE-RELEASE-R033.4
    step = _steps()["Publish by trusted publishing"]
    assert step["if"] == "steps.mode.outputs.mode == 'oidc'"
    assert step["env"] == {"NODE_AUTH_TOKEN": ""}
    assert "NPM_TOKEN" not in step["run"]
