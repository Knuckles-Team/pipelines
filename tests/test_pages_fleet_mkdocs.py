"""Malformed MkDocs input must never turn an exact-ref receipt into a pass."""

import pytest

from scripts.pages_fleet_parity import verify
from pages_fleet_fixtures import fleet_fixture, revise
from pages_fleet_assertions import assert_unverified_receipt, replace_workflow


@pytest.mark.parametrize("payload,reason", [
    ("docs_dir: docs\ndocs_dir: other\n", "mkdocs-duplicate-key"),
    ("docs_dir: [\n", "mkdocs-yaml-invalid"),
    ("defaults: &d {docs_dir: other}\n<<: *d\n", "mkdocs-merge-key"),
    ("defaults: &d {extra: {docs_dir: other}}\n<<: *d\n", "mkdocs-merge-key"),
    ("docs_dir: docs\n<<: {docs_dir: other}\ndocs_dir: docs\n", "mkdocs-merge-key"),
    ("!custom {site_name: Fixture}\n", "mkdocs-mapping-required"),
    ("docs_dir: !custom docs\n", "content-source-docs-dir-invalid"),
])
def test_invalid_mkdocs_yields_unverified_receipt(tmp_path, capsys, payload, reason):
    declaration = fleet_fixture(tmp_path)
    changed = revise(tmp_path, declaration, lambda target: (target / "mkdocs.yml").write_text(payload))
    result = verify(changed, tmp_path)
    assert result["status"] == "unverified"
    assert result["consumers"][0]["reason"] == reason
    assert_unverified_receipt(tmp_path, changed, capsys)


@pytest.mark.parametrize("old,new,expected", [
    ("example/pipelines", "EXAMPLE/PIPELINES", "pass"),
    ("pages_pipeline.yml", "Pages_pipeline.yml", "unverified"),
])
def test_workflow_case_rules(tmp_path, old, new, expected):
    declaration = fleet_fixture(tmp_path)

    changed = replace_workflow(tmp_path, declaration, old, new)
    assert verify(changed, tmp_path)["status"] == expected
