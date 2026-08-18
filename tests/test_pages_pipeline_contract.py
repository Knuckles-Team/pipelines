"""Focused workflow contracts for CONCEPT:ECO-4.DOCS-DELIVERY."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


WORKFLOW = Path(__file__).parents[1] / ".github/workflows/pages_pipeline.yml"


def _workflow() -> dict:
    parsed = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    # YAML 1.1 loaders treat the unquoted workflow key ``on`` as boolean.
    value = parsed.get("on", parsed.get(True))
    assert isinstance(value, dict)
    return {"document": parsed, "on": value}


def test_readiness_is_explicit_opt_in_with_bounded_paths() -> None:
    contract = _workflow()
    inputs = contract["on"]["workflow_call"]["inputs"]
    assert inputs["agent_readiness_enabled"] == {
        "description": "Deliberately enable canonical source-Markdown readiness delivery.",
        "required": False,
        "type": "boolean",
        "default": False,
    }
    assert inputs["readiness_manifest"]["default"] == "agent-readiness-manifest.json"
    assert inputs["markdown_manifest"]["default"] == "markdown-mirror-manifest.json"
    assert inputs["readiness_schema"]["default"] == "docs/agent-readiness.schema.json"
    assert inputs["readiness_input"]["default"] == "docs/agent-readiness.json"


def test_actions_are_immutable_and_permissions_are_least_privilege() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    refs = re.findall(r"uses:\s+[^\s@]+@([0-9a-f]{40})(?:\s|$|#)", text)
    assert len(refs) == 6
    assert "mkdocs-material==9.7.6" in text
    assert "mkdocs-awesome-pages-plugin==2.10.1" in text
    assert "contents: write" not in text
    assert "permissions: write-all" not in text
    assert "persist-credentials: false" in text


def test_enabled_path_checks_strict_build_and_runs_owned_tck() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "if: inputs.agent_readiness_enabled" in text
    assert "mkdocs build --strict" in text
    assert "python .pipeline-contract/scripts/pages_readiness.py build" in text
    assert "python .pipeline-contract/scripts/pages_readiness.py tck" in text
    assert "repository: ${{ job.workflow_repository }}" in text
    assert "ref: ${{ job.workflow_sha }}" in text
    assert 'echo "$READINESS' not in text
