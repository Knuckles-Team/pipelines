"""Focused workflow contracts for Spec: PIPE-PAGES-R043."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
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
            "Deliberately inherit the shared Pages theme (Material config, "
            "markdown extensions, generated styles, logo, footer, switcher, and "
            "landing-page assets) from this repository's "
            "templates/mkdocs-theme/base.mkdocs.yml via mkdocs's native "
            "INHERIT:. The caller's own mkdocs.yml declares its content manifest; "
            "committed generated assets are checked against this immutable workflow ref."
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


def test_write_scopes_are_held_only_by_the_deploy_job() -> None:
    document = _workflow()["document"]
    assert document["permissions"] == {"contents": "read"}
    assert document["jobs"]["deploy"]["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }


# spec: PIPE-PAGES-R043.3
def test_enabled_path_checks_strict_build_and_runs_owned_tck() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "if: inputs.agent_readiness_enabled" in text
    assert "mkdocs build --strict" in text
    assert "for mode in build tck; do" in text
    assert 'python .pipeline-contract/scripts/pages_readiness.py "$mode"' in text
    assert "--content-source" in text
    assert "repository: ${{ job.workflow_repository }}" in text
    assert "ref: ${{ job.workflow_sha }}" in text
    assert 'echo "$READINESS' not in text


def test_content_source_is_validated_before_any_declared_authority_is_trusted() -> None:
    """The workflow delegates content_source validation to the tested helper.

    The check itself (empty/missing/mismatched content_source) lives in
    `scripts/pages_readiness.py::validate_content_source` -- see
    `test_pages_readiness.py` -- so it is unit-tested rather than only
    grep-able workflow text. This asserts the workflow actually calls it,
    with the script checked out before it can be invoked, and gated the
    same as the feature(s) that need it.
    """

    text = WORKFLOW.read_text(encoding="utf-8")
    assert "if: inputs.shared_theme_enabled || inputs.agent_readiness_enabled" in text
    assert "python .pipeline-contract/scripts/pages_readiness.py validate-content-source" in text
    assert "Checkout pipeline-owned scripts" in text


def test_pipeline_checkout_includes_the_split_readiness_package() -> None:
    document = _workflow()["document"]
    checkout = next(
        step for step in document["jobs"]["deploy"]["steps"] if step.get("name") == "Checkout pipeline-owned scripts"
    )
    assert checkout["with"]["sparse-checkout"].splitlines() == [
        "scripts/__init__.py",
        "scripts/pages_readiness.py",
        "scripts/spec_dashboard.py",
        "scripts/spec_dashboard_render.py",
        "scripts/spec_dashboard_sources.py",
        "scripts/spec_dashboard_definitions.py",
        "scripts/spec_dashboard_panels.py",
        "scripts/spec_dashboard_records.py",
        "scripts/spec_dashboard_structure.py",
        "scripts/spec_dashboard_style.py",
        "scripts/spec_dashboard_nav.py",
        "scripts/spec_dashboard_drilldown.py",
        "scripts/skill_graph/__init__.py",
        "scripts/skill_graph/model.py",
        "scripts/spec_dashboard_concepts.py",
        "scripts/spec_dashboard_relations.py",
        "scripts/spec_dashboard_relations_view.py",
        "scripts/spec_dashboard_wiring.py",
        "scripts/spec_dashboard_metadata.py",
        "scripts/spec_dashboard_links.py",
        "scripts/spec_dashboard_architecture.py",
        "scripts/spec_graph_core.py",
        "scripts/spec_graph_load.py",
        "scripts/spec_graph_parse.py",
        "scripts/readiness",
        "scripts/architecture_explorer",
        "pipelines_hooks/__init__.py",
        "pipelines_hooks/core/__init__.py",
        "pipelines_hooks/core/repositories.py",
        "pipelines_hooks/specs/__init__.py",
        "pipelines_hooks/specs/ids.py",
        "pipelines_hooks/specs/priority.py",
        "pipelines_hooks/specs/requirements_doc.py",
    ]


def test_shared_theme_inherits_via_mkdocs_native_inherit_key() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "templates/mkdocs-theme/base.mkdocs.yml" in text
    assert "templates/mkdocs-theme" in text
    assert "scripts/sync_mkdocs_theme.py" in text
    assert "INHERIT:" in text
    assert "Verify shared Pages theme assets" in text
    assert "sync_mkdocs_theme.py check" in text


def test_spec_dashboard_is_opt_in_and_after_readiness():
    contract = _workflow()
    inputs = contract["on"]["workflow_call"]["inputs"]
    assert inputs["spec_dashboard_enabled"]["default"] is False
    text = WORKFLOW.read_text()
    assert "scripts/spec_dashboard.py" in text
    assert text.index("Build spec delivery snapshot") > text.index("Publish readiness assets")
    assert text.index("Build spec delivery snapshot") < text.index("Upload artifact")
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert '--repository "$GITHUB_REPOSITORY"' in text


def test_dashboard_checkout_is_shallow():
    steps = _workflow()["document"]["jobs"]["deploy"]["steps"]
    checkout = next(step for step in steps if step["name"] == "Checkout Repository")
    assert checkout["with"]["fetch-depth"] == 1
    assert checkout["with"]["persist-credentials"] is False


def test_dashboard_caller_checkout_materializes_source_files():
    document = _workflow()["document"]
    checkout = next(step for step in document["jobs"]["deploy"]["steps"] if step.get("name") == "Checkout Repository")
    assert "sparse-checkout" not in checkout["with"]
    assert checkout["with"]["fetch-depth"] == 1


@pytest.mark.spec("PIPE-PAGES-R042")
def test_architecture_explorer_defaults_to_core_repositories_and_builds_before_upload() -> None:
    contract = _workflow()
    inputs = contract["on"]["workflow_call"]["inputs"]
    assert inputs["architecture_explorer"]["default"] == "auto"
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "medulla|arbora|scion-sdk|meristem|tuig|overstory|pipelines|universal-skills" in text
    assert text.index("Build architecture explorer") < text.index("Upload artifact")
    assert "--page site/architecture/index.html" in text
    assert "npm ci --prefix .pipeline-contract/scripts/architecture_explorer" in text
    assert "ARCHITECTURE_EXPLORER_ENABLED: ${{ steps.explorer.outputs.enabled }}" in text
    assert "build.py --redirect" in text and "on) enabled=true; build=true ;;" in text
    assert "org_site_dispatch_token" not in text, "the dispatch lives only in notify_org_site.yml"


NOTIFY = Path(__file__).parents[1] / ".github/workflows/notify_org_site.yml"


def _run(script: str, env: dict) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)


@pytest.mark.spec("PIPE-PAGES-R042")
def test_notify_org_site_is_the_single_app_dispatch_and_exits_zero_without_the_app(tmp_path) -> None:
    """One dispatch, authenticated as a pinned GitHub App; every missing or failing part only warns."""
    contract = yaml.safe_load(NOTIFY.read_text(encoding="utf-8"))
    secrets = contract[True]["workflow_call"]["secrets"]
    assert set(secrets) == {"org_site_app_id", "org_site_app_private_key"}
    assert all(v["required"] is False for v in secrets.values())
    job = contract["jobs"]["notify"]
    assert job["runs-on"] == "ubuntu-latest"
    skip, mint, send = job["steps"]
    assert skip["if"] == mint["if"].replace("==", "!=") == send["if"].replace("==", "!=")
    assert re.fullmatch(r"actions/create-github-app-token@[0-9a-f]{40}", mint["uses"])
    assert mint["with"]["owner"] == "Knuckles-Team" and mint["with"]["repositories"] == ".github"
    assert "/repos/Knuckles-Team/.github/dispatches" in send["run"] and "specs-changed" in send["run"]
    base = {"PATH": os.environ["PATH"], "SOURCE_REPOSITORY": "o/r", "SOURCE_SHA": "abc"}
    notice = _run(skip["run"], base)
    assert notice.returncode == 0 and "::notice::" in notice.stdout
    nomint = _run(send["run"], {**base, "DISPATCH_TOKEN": ""})
    assert nomint.returncode == 0 and "::warning::" in nomint.stdout
    fake = tmp_path / "curl"
    fake.write_text("#!/bin/sh\nexit 22\n")
    fake.chmod(0o755)
    failed = _run(send["run"], {**base, "DISPATCH_TOKEN": "x", "PATH": f"{tmp_path}:{base['PATH']}"})
    assert failed.returncode == 0 and "::warning::" in failed.stdout


@pytest.mark.spec("PIPE-PAGES-R042")
@pytest.mark.parametrize("omit_repository_identity", [False, True])
def test_explorer_imports_from_only_declared_sparse_python_files(
    tmp_path: Path, omit_repository_identity: bool
) -> None:
    """No installed pipelines package or full checkout can mask a missing import."""
    steps = _workflow()["document"]["jobs"]["deploy"]["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout pipeline-owned scripts")
    root = WORKFLOW.parents[2]
    for declared in checkout["with"]["sparse-checkout"].splitlines():
        source = root / declared
        files = source.rglob("*.py") if source.is_dir() else [source]
        for path in files:
            relative = path.relative_to(root)
            if omit_repository_identity and relative.as_posix() == "pipelines_hooks/core/repositories.py":
                continue
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(tmp_path / "scripts/architecture_explorer/build.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if omit_repository_identity:
        assert result.returncode != 0
        assert "ModuleNotFoundError: No module named 'pipelines_hooks.core.repositories'" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert "--mode" in result.stdout
