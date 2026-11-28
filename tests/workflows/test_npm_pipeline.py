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
    for name in ("Verify the tag version", "Pre-publish", "Publish"):
        condition = steps[name]["if"]
        assert "inputs.publish" in condition and "refs/tags/v" in condition, name
    assert "npm publish --provenance --access public" in steps["Publish"]["run"]
    assert "pipelines-hook npm-tag-version" in steps["Verify the tag version"]["run"]
    for gate in ("Typecheck", "Lint", "Test", "Build"):
        assert "GATE_FAILED" in steps[gate]["run"], gate
    order = list(steps)
    assert (
        order.index("Build")
        < order.index("Verify the tag version")
        < order.index("Pre-publish")
        < order.index("Publish")
    )
    assert document["jobs"]["npm"]["permissions"]["id-token"] == "write"
