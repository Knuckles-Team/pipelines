"""PIPE-GATES-R101: every custom ontology IRI lives under the one ontology base."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.cli import main
from pipelines_hooks.hygiene.ontology_iri import BASE, CORE_PRODUCT_NAMES, judge, scan, workspace_names
from tests.hooks.conftest import Repo

# Retired namespaces are assembled so this tracked test does not itself break the gate.
OLD_HTTP = "http://" + "knuckles.team/kg#"
OLD_HOST = "http://" + "medulla/owl#"
NAMES = frozenset(CORE_PRODUCT_NAMES)


def _kinds(repo: Repo) -> list[str]:
    return [finding.kind for finding in scan(repo.root, NAMES)]


# spec: PIPE-GATES-R101
def test_the_base_namespace_passes(repo: Repo) -> None:
    repo.stage({"o.ttl": f"@prefix : <{BASE}core#> .\n<{BASE}core> a owl:Ontology .\n"})
    assert scan(repo.root, NAMES) == []
    assert repo.run("ontology-iri") == 0


# spec: PIPE-GATES-R101
def test_an_http_custom_namespace_fails(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.stage({"o.ttl": f"@prefix kg: <{OLD_HTTP}> .\n"})
    assert repo.run("ontology-iri") == 1
    assert f"o.ttl:1: http-namespace: {OLD_HTTP}" in capsys.readouterr().out


# spec: PIPE-GATES-R101
def test_a_custom_https_namespace_outside_the_base_fails(repo: Repo) -> None:
    repo.stage(
        {
            "o.ttl": "PREFIX x: <https://example-corp.dev/vocab#>\n",
            "b.ttl": "@prefix y: <https://knuckles-team.github.io/scion-sdk/stream#> .\n",
        }
    )
    assert _kinds(repo) == ["outside-base", "outside-base"]


# spec: PIPE-GATES-R101
@pytest.mark.parametrize(
    "module", ["medulla", "arbora", "scion-sdk", "Meristem", "caddy-mcp", "github-agent", "x/jira-api"]
)
def test_a_product_or_package_name_segment_fails(module: str) -> None:
    assert judge(f"{BASE}{module}#", NAMES, example_ok=False) == "product-name-segment"


# spec: PIPE-GATES-R101
@pytest.mark.parametrize(
    "module", ["core", "harness", "decision", "connector/qbittorrent", "data-platform", "state-machines"]
)
def test_domain_modules_pass(module: str) -> None:
    assert judge(f"{BASE}{module}#", NAMES, example_ok=False) is None


# spec: PIPE-GATES-R101
@pytest.mark.parametrize("module", ["core/v1", "core/1.2.0", "core-v2", "core/2026-11-12", "v3/core"])
def test_a_versioned_namespace_fails_but_the_version_iri_passes(module: str, repo: Repo) -> None:
    assert judge(f"{BASE}{module}#", NAMES, example_ok=False) == "versioned-namespace"
    repo.stage({"o.ttl": f"<{BASE}core> owl:versionIRI <{BASE}core/1.2.0> .\n"})
    assert scan(repo.root, NAMES) == []


# spec: PIPE-GATES-R101
@pytest.mark.parametrize(
    "iri",
    [
        "http://www.w3.org/2002/07/owl#",
        "https://schema.org/",
        "http://purl.org/dc/terms/",
        "http://purl.obolibrary.org/obo/BFO_",
        "https://spec.edmcouncil.org/fibo/ontology/FND/Organizations/Organizations/",
        "http://www.opengis.net/ont/geosparql#",
    ],
)
def test_standard_vocabularies_are_allowed(iri: str) -> None:
    assert judge(iri, NAMES, example_ok=False) is None


# spec: PIPE-GATES-R101
def test_example_hosts_are_allowed_under_test_paths_only(repo: Repo) -> None:
    repo.stage(
        {"tests/f.ttl": "@prefix ex: <http://example.org/> .\n", "src/f.ttl": "@prefix ex: <http://example.org/> .\n"}
    )
    hits = scan(repo.root, NAMES)
    assert [(hit.path, hit.kind) for hit in hits] == [("src/f.ttl", "http-namespace")]


# spec: PIPE-GATES-R101
def test_namespace_constants_and_legacy_hosts_in_code_are_found(repo: Repo) -> None:
    repo.stage(
        {
            "a.rs": f'pub const OWL_NAMESPACE: &str = "{OLD_HOST}";\n',
            "b.py": 'ONTOLOGY_BASE = "https://other.example.dev/onto#"\n',
            "c.py": f'q = "SELECT * WHERE {{ ?s a <{OLD_HTTP}Agent> }}"\n',
            "d.py": 'DOC = "https://github.com/org/repo/blob/main/x.md"\nPLAIN = "https://api.service.dev/v1/things"\n',
        }
    )
    hits = {(hit.path, hit.kind) for hit in scan(repo.root, NAMES)}
    assert hits == {("a.rs", "http-namespace"), ("b.py", "outside-base"), ("c.py", "http-namespace")}


# spec: PIPE-GATES-R101
def test_the_repository_name_is_a_product_name(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.stage({"o.ttl": f"@prefix : <{BASE}{repo.root.name}#> .\n"})
    assert main(["ontology-iri", str(repo.root)]) == 1
    assert "product-name-segment" in capsys.readouterr().out


# spec: PIPE-GATES-R101
def test_workspace_manifest_repository_names_are_read(tmp_path: Path) -> None:
    manifest = tmp_path / "workspace.yml"
    manifest.write_text(
        "repositories:\n- url: https://github.com/Org/leanix-agent.git\n  description: x\n- url: https://example.invalid/x/Plain\n",
        encoding="utf-8",
    )
    assert workspace_names(manifest) == frozenset({"leanix-agent", "plain"})
    assert workspace_names(None) == frozenset()


# spec: PIPE-GATES-R101
def test_every_workspace_repository_name_is_rejected_as_a_segment() -> None:
    manifest = Path(__file__).resolve().parents[3] / "workspace.yml"
    if not manifest.is_file():
        pytest.skip("no workspace manifest next to this checkout")
    names = workspace_names(manifest)
    assert names
    assert all(judge(f"{BASE}{name}#", names, example_ok=False) == "product-name-segment" for name in names)
