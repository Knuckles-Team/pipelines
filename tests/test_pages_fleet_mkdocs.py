"""Malformed MkDocs input must never turn an exact-ref receipt into a pass."""

import json

import pytest

from scripts.check_five_repo_parity import main
from scripts.pages_fleet_parity import verify
from pages_fleet_fixtures import declaration_file, fleet_fixture, revise


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
    path = declaration_file(tmp_path / "declaration", changed)
    assert main(["--declaration", str(path), "--fixtures", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["verification"]["status"] == "unverified"


@pytest.mark.parametrize("old,new,expected", [
    ("example/pipelines", "EXAMPLE/PIPELINES", "pass"),
    ("pages_pipeline.yml", "Pages_pipeline.yml", "unverified"),
])
def test_workflow_case_rules(tmp_path, old, new, expected):
    declaration = fleet_fixture(tmp_path)

    def mutate(target):
        path = target / ".github/workflows/pages.yml"
        path.write_text(path.read_text().replace(old, new))

    changed = revise(tmp_path, declaration, mutate)
    assert verify(changed, tmp_path)["status"] == expected
