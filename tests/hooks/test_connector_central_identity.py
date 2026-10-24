"""Identity rules of the central connector migration: connector names and own-workflow refs (PIPE-GATES-R016.100, .101)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.hygiene.connector_central import identity
from pipelines_hooks.hygiene.connector_central.base import Ctx, Review

PYPROJECT = '[project]\nname = "demo-agent"\nversion = "1.0.0"\n\n[project.entry-points."agent_connector_sdk.connector"]\ndemo-mcp = "demo_agent:connector"\n'


def _ctx(tmp_path: Path) -> Ctx:
    root = tmp_path / "r"
    (root / "demo_agent/ontology/mappings").mkdir(parents=True)
    (root / ".github/workflows").mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    return Ctx(root=root, pkg=root / "demo_agent", fleet="demo-mcp", dist="demo-agent", review=Review())


@pytest.mark.spec("PIPE-GATES-R016.100")
def test_name_mismatch_derives_from_the_sdk_identity_and_mapping_yaml_follows(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    kg = ctx.pkg / "kg_ingest.py"
    kg.write_text('import os\n\n_SOURCE = "demo-agent"\n_X = 1\n', encoding="utf-8")
    (ctx.pkg / "kg_media.py").write_text('_SOURCE = "demo-mcp"\n', encoding="utf-8")
    y = ctx.pkg / "ontology/mappings/source.yaml"
    y.write_text("schema_version: 2\nconnector: demo-agent\n", encoding="utf-8")
    identity.connector_names(ctx)
    text = kg.read_text(encoding="utf-8")
    assert '_SOURCE = connector_name("demo_agent")' in text and "import connector_name" in text
    assert (ctx.pkg / "kg_media.py").read_text(encoding="utf-8") == '_SOURCE = "demo-mcp"\n'
    assert "connector: demo-mcp" in y.read_text(encoding="utf-8")
    again = kg.read_text(encoding="utf-8")
    identity.connector_names(ctx)
    assert kg.read_text(encoding="utf-8") == again


@pytest.mark.spec("PIPE-GATES-R016.101")
def test_own_workflow_refs_are_main(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    wf = ctx.root / ".github/workflows/connector-pr.yml"
    wf.write_text(
        "jobs:\n  gates:\n    uses: Knuckles-Team/pipelines/.github/workflows/connector_pr_pipeline.yml@latest\n"
        "  other:\n    uses: actions/checkout@v4\n",
        encoding="utf-8",
    )
    identity.workflow_refs(ctx)
    text = wf.read_text(encoding="utf-8")
    assert "connector_pr_pipeline.yml@main" in text and "actions/checkout@v4" in text
    identity.workflow_refs(ctx)
    assert wf.read_text(encoding="utf-8") == text


@pytest.mark.spec("PIPE-GATES-R016.103")
def test_org_site_workflow_is_written_only_when_pipelines_provides_the_shared_one(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    pl = tmp_path / "pl"
    (pl / ".github/workflows").mkdir(parents=True)
    ctx.options["pipelines_root"] = pl
    identity.org_site(ctx)
    assert not (ctx.root / ".github/workflows/org-site.yml").exists()
    (pl / ".github/workflows/notify_org_site.yml").write_text("name: x\n", encoding="utf-8")
    identity.org_site(ctx)
    text = (ctx.root / ".github/workflows/org-site.yml").read_text(encoding="utf-8")
    assert text == identity.ORG_SITE and "secrets: inherit" in text
    ctx.applied.clear()
    identity.org_site(ctx)
    assert not ctx.applied
