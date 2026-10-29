"""The pipeline provider publishes its own specs through its single Pages caller."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_provider_enables_dashboard_and_canonical_config():
    workflow = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text())
    job = workflow["jobs"]["deploy"]
    assert workflow["name"] == "Pages"
    assert job["uses"] == "./.github/workflows/pages_pipeline.yml"
    assert job["with"]["spec_dashboard_enabled"] is True
    assert job["with"]["shared_theme_enabled"] is True
    config = ROOT / job["with"]["spec_dashboard_config"]
    assert json.loads(config.read_text()) == {
        "version": 1,
        "sources": [{"glob": "specs/*/status.json", "kind": "spec"}],
    }
    assert job["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}


def test_provider_deploys_on_version_tags():
    workflow = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"] == {"tags": ["v*"]}
    assert "workflow_dispatch" in triggers


def test_provider_retains_one_pages_publisher_and_discovery_link():
    workflows = list((ROOT / ".github/workflows").glob("*.yml"))
    callers = [path.name for path in workflows if "uses: ./.github/workflows/pages_pipeline.yml" in path.read_text()]
    deployers = [path.name for path in workflows if "uses: actions/deploy-pages@" in path.read_text()]
    assert callers == ["pages.yml"]
    assert deployers == ["pages_pipeline.yml"]
    url = "https://knuckles-team.github.io/pipelines/spec-delivery/"
    assert url in (ROOT / "mkdocs.yml").read_text()
    assert url in (ROOT / "pages/index.md").read_text()
