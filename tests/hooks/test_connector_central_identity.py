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


@pytest.mark.spec("PIPE-GATES-R016.104")
def test_unindexed_local_spec_is_added_to_the_readme_index(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.root / "specs/connector-content").mkdir(parents=True)
    (ctx.root / "specs/connector-content/spec.md").write_text(
        "# CONN-DEMO-CONNECTOR-CONTENT — The connector serves its packaged content\n\nOwner: demo.\n", encoding="utf-8"
    )
    readme = ctx.root / "specs/README.md"
    readme.write_text(
        "# specs\n\n## Local specifications\n\nThis repository has no local spec yet.\n", encoding="utf-8"
    )
    identity.spec_index(ctx)
    text = readme.read_text(encoding="utf-8")
    assert "- [`CONN-DEMO-CONNECTOR-CONTENT`](connector-content/spec.md)" in text and "no local spec yet" not in text
    identity.spec_index(ctx)
    assert readme.read_text(encoding="utf-8") == text


@pytest.mark.spec("PIPE-GATES-R016.105")
def test_missing_theme_files_are_synced_from_the_canonical_copy_and_a_second_run_is_a_no_op(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.root / "mkdocs.yml").write_text("site_name: demo\n", encoding="utf-8")
    (ctx.root / "docs").mkdir()
    identity.theme_files(ctx)
    logo = ctx.root / "docs/assets/brands/arbora-logo-v1.png"
    assert logo.is_file() and "docs/assets/brands/arbora-logo-v1.png" in ctx.changed and "pl.aa" in ctx.applied
    ctx.applied.clear()
    identity.theme_files(ctx)
    assert not ctx.applied
    (ctx.root / "docs/assets/brands/arbora-logo-v1.png").unlink()
    identity.theme_files(ctx)
    assert logo.is_file()


@pytest.mark.spec("PIPE-GATES-R016.105")
def test_no_mkdocs_site_means_no_theme_files(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    identity.theme_files(ctx)
    assert not (ctx.root / "docs").exists() and not ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.106")
def test_authors_block_becomes_the_neutral_organisation_author_and_passes_the_privacy_classifier(
    tmp_path: Path,
) -> None:
    from pipelines_hooks.privacy import classify

    ctx = _ctx(tmp_path)
    pp = ctx.root / "pyproject.toml"
    pp.write_text(
        pp.read_text(encoding="utf-8")
        + '\n[[project.authors]]\nname = "Some Person"\nemail = "p@home.example"\n\n[tool.x]\na = 1\n',
        encoding="utf-8",
    )
    identity.neutral_author(ctx)
    text = pp.read_text(encoding="utf-8")
    assert f'name = "{identity.NEUTRAL_AUTHOR_NAME}"' in text and f'email = "{identity.NEUTRAL_AUTHOR_EMAIL}"' in text
    assert "[tool.x]" in text and classify.author_metadata_lines(pp, text.splitlines()) == []
    ctx.applied.clear()
    identity.neutral_author(ctx)
    assert not ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.106")
def test_authors_block_with_other_fields_is_reviewed_untouched(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    pp = ctx.root / "pyproject.toml"
    pp.write_text(pp.read_text(encoding="utf-8") + '\n[[project.authors]]\nname = "A"\nurl = "x"\n', encoding="utf-8")
    before = pp.read_text(encoding="utf-8")
    identity.neutral_author(ctx)
    assert pp.read_text(encoding="utf-8") == before and ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.107")
def test_example_credential_uris_in_docs_code_become_the_gate_placeholder_form(tmp_path: Path) -> None:
    from pipelines_hooks.privacy.patterns import credential_uri_leak

    SECRET = "s3cret" + "value"  # sanitizer:ignore - synthetic fixture credential
    ctx = _ctx(tmp_path)
    (ctx.root / "docs").mkdir()
    doc = ctx.root / "docs/platform.md"
    doc.write_text(
        f"Prose keeps postgresql://realuser:{SECRET}@db.example.com/x as is.\n\n```yaml\n"  # sanitizer:ignore - synthetic fixture credential
        f'  DATABASE_URL: "postgresql://plane:{SECRET}@plane-db/plane"\n  OK: "amqp://u:changeme@mq"\n```\n\n'  # sanitizer:ignore - synthetic fixture credential
        f"Inline `redis://app:{SECRET}@cache:6379/0` too.\n",  # sanitizer:ignore - synthetic fixture credential
        encoding="utf-8",
    )
    (ctx.root / ".env").write_text(
        f"DATABASE_URL=postgresql://plane:{SECRET}@db/x\n", encoding="utf-8"
    )  # sanitizer:ignore - synthetic fixture credential
    identity.docs_credential_examples(ctx)
    text = doc.read_text(encoding="utf-8")
    assert (
        "postgresql://USER:PASSWORD@plane-db/plane" in text and "`redis://USER:PASSWORD@cache:6379/0`" in text
    )  # sanitizer:ignore - synthetic fixture credential
    assert (
        "amqp://u:changeme@mq" in text and f"postgresql://realuser:{SECRET}@db.example.com/x" in text
    )  # sanitizer:ignore - synthetic fixture credential
    assert (ctx.root / ".env").read_text(encoding="utf-8").count(f"{SECRET}") == 1
    assert not any(
        credential_uri_leak(ln) for ln in text.splitlines() if ln.strip().startswith(("DATABASE_URL", "Inline"))
    )
    ctx.applied.clear()
    identity.docs_credential_examples(ctx)
    assert not ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.107")
def test_internal_hostnames_in_tests_become_the_reserved_example_form(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.root / "tests").mkdir()
    t = ctx.root / "tests/test_auth.py"
    t.write_text(
        'BASE = "https://aris.internal/abs/api"\nOK = "https://svc.example.com"\nK = "db.ns.svc.cluster.local"\n'
        'assert BASE.startswith("https://aris.internal")\nx = ipmi.lan("print")\nT = "http://{host}.lan:9180"\n',
        encoding="utf-8",
    )
    identity.docs_credential_examples(ctx)
    text = t.read_text(encoding="utf-8")
    assert "https://aris.example/abs/api" in text and 'startswith("https://aris.example")' in text
    assert "db.ns.svc.cluster.example" in text and "https://svc.example.com" in text
    assert ".internal" not in text and 'ipmi.lan("print")' in text
    assert 'T = "http://{host}.example:9180"' in text
    ctx.applied.clear()
    identity.docs_credential_examples(ctx)
    assert not ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.108")
def test_mutable_checkout_and_setup_python_tags_become_the_fleet_pins(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    wf = ctx.root / ".github/workflows/docs.yml"
    wf.write_text(
        "jobs:\n  d:\n    steps:\n      - uses: actions/checkout@v4\n        with:\n          fetch-depth: 0\n"
        "      - uses: actions/setup-python@v5\n      - uses: other/action@v1\n",
        encoding="utf-8",
    )
    identity.pin_actions(ctx)
    text = wf.read_text(encoding="utf-8")
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1" in text
    assert (
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0" in text and "other/action@v1" in text
    )
    ctx.applied.clear()
    identity.pin_actions(ctx)
    assert not ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.109")
def test_publication_workflow_test_expects_the_shared_main_revision(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.root / "tests").mkdir()
    test = ctx.root / "tests/test_publication_workflow.py"
    test.write_text(
        'CONTRACT = "0123456789abcdef"\n\n\ndef test_x(repo):\n    assert repo["repo"] == "u"\n    assert repo["rev"] == CONTRACT\n',
        encoding="utf-8",
    )
    identity.publication_test_rev(ctx)
    assert 'assert repo["rev"] == "main"' in test.read_text(encoding="utf-8")
    ctx.applied.clear()
    identity.publication_test_rev(ctx)
    assert not ctx.applied
