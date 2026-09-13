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


def test_content_source_declares_the_authority_and_defaults_to_pages() -> None:
    contract = _workflow()
    inputs = contract["on"]["workflow_call"]["inputs"]
    assert inputs["content_source"]["default"] == "pages"
    assert inputs["content_source"]["required"] is False
    assert inputs["content_source"]["type"] == "string"


def test_shared_theme_is_explicit_opt_in() -> None:
    contract = _workflow()
    inputs = contract["on"]["workflow_call"]["inputs"]
    assert inputs["shared_theme_enabled"] == {
        "description": (
            "Deliberately inherit the one shared Pages theme (Material "
            "config, markdown extensions, CSS) from this repository's "
            "templates/mkdocs-theme/base.mkdocs.yml via mkdocs's native "
            "INHERIT:, so the caller's own mkdocs.yml only needs to declare "
            "its content manifest (site_name/site_url/nav/docs_dir)."
        ),
        "required": False,
        "type": "boolean",
        "default": False,
    }


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
    assert inputs["readiness_schema"]["default"] == "pages/agent-readiness.schema.json"
    assert inputs["readiness_input"]["default"] == "pages/agent-readiness.json"


def test_actions_are_immutable_and_permissions_are_least_privilege() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    refs = re.findall(r"uses:\s+[^\s@]+@([0-9a-f]{40})(?:\s|$|#)", text)
    assert len(refs) == 7
    assert "python-version: 3.14.7" in text
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
    assert "--content-source" in text
    assert "repository: ${{ job.workflow_repository }}" in text
    assert "ref: ${{ job.workflow_sha }}" in text
    assert 'echo "$READINESS' not in text


def test_content_source_is_validated_before_any_declared_authority_is_trusted() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "if: inputs.shared_theme_enabled || inputs.agent_readiness_enabled" in text
    assert "content_source must not be empty" in text
    assert "does not exist in this repository" in text
    assert "docs_dir" in text


def test_shared_theme_inherits_via_mkdocs_native_inherit_key() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "templates/mkdocs-theme/base.mkdocs.yml" in text
    assert "templates/mkdocs-theme/extra.css" in text
    assert "INHERIT:" in text
