"""connector-surface-audit static levels (PIPE-GATES-R014)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.hygiene import connector_surface as audit

pytestmark = pytest.mark.spec("PIPE-GATES-R014")

PARENT = """@prefix : <http://knuckles.team/kg#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://knuckles.team/kg/core> a owl:Ontology ; rdfs:comment "parent # not a comment ." .
:Document a owl:Class ; rdfs:label "Document" .
:Ticket a owl:Class .
"""

LINKED = """@prefix : <http://knuckles.team/kg#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://knuckles.team/kg/demo> a owl:Ontology ; owl:imports <http://knuckles.team/kg> .
:Incident a owl:Class ; rdfs:comment \"\"\"A ticket.
Spans lines.\"\"\" ; rdfs:subClassOf :Ticket .
:MajorIncident a owl:Class ; rdfs:subClassOf :Incident .
"""

ORPHAN = """@prefix d: <http://example.org/demo#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
d:Widget a owl:Class .
"""

PYPROJECT = """[project]
name = "demo-mcp"
[project.entry-points."scion_sdk.connector"]
demo-mcp = "demo_mcp"
[project.entry-points."scion_sdk.skill_providers"]
demo-mcp = "demo_mcp.skills"
[project.entry-points."scion_sdk.prompt_providers"]
demo-mcp = "demo_mcp.prompts"
[project.entry-points."scion_sdk.ontology_providers"]
demo-mcp = "demo_mcp.ontology"
"""

SERVER = """from scion_sdk.mcp.content import ConnectorContent
from scion_sdk.mcp.server import create_mcp_server
create_mcp_server(name="demo", content=ConnectorContent(connector="demo-mcp", package_root=".", package_version="1"))
"""


def _connector(root: Path, ontology: str = LINKED, server: str = SERVER) -> Path:
    pkg = root / "demo_mcp"
    (pkg / "skills" / "demo-read").mkdir(parents=True)
    (pkg / "skills" / "demo-read" / "SKILL.md").write_text("---\nname: demo-read\n---\n")
    (pkg / "prompts").mkdir()
    (pkg / "prompts" / "triage.json").write_text(json.dumps({"instructions": {"core_directive": "Triage."}}))
    (pkg / "ontology" / "shapes").mkdir(parents=True)
    (pkg / "ontology" / "demo.ttl").write_text(ontology)
    (pkg / "ontology" / "shapes" / "demo.shacl.ttl").write_text("")
    (pkg / "mcp_server.py").write_text(server)
    (root / "pyproject.toml").write_text(PYPROJECT)
    return root


def _parents(tmp_path: Path) -> set[str]:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "core-v1.ttl").write_text(PARENT)
    return audit.parent_terms(parent)


def test_parser_keeps_hash_iris_and_ignores_literals(tmp_path: Path) -> None:
    assert _parents(tmp_path) == {"http://knuckles.team/kg#Document", "http://knuckles.team/kg#Ticket"}


def test_complete_connector_has_no_gaps(tmp_path: Path) -> None:
    record = audit.audit_connector(_connector(tmp_path / "demo-mcp"), _parents(tmp_path))
    assert record["gaps"] == []
    assert record["complete"] and record["served"] and record["pack_complete"] and record["parent_linked"]
    assert record["counts"] == {"ontology": 1, "prompts": 1, "prompts_valid": 1, "shapes": 1, "skills": 1}
    (report,) = record["ontology"]
    assert report["imports_parent"] and report["linked"] == 2 and report["orphans"] == []


def test_orphan_vocabulary_is_flagged(tmp_path: Path) -> None:
    record = audit.audit_connector(_connector(tmp_path / "demo-mcp", ontology=ORPHAN), _parents(tmp_path))
    assert not record["parent_linked"]
    assert record["ontology"][0]["orphans"] == ["http://example.org/demo#Widget"]
    assert "ontology not linked to the parent ontology" in record["gaps"]


def test_unserved_content_and_foreign_groups_are_gaps(tmp_path: Path) -> None:
    root = _connector(tmp_path / "demo-mcp", server="create_mcp_server(name='demo')\n")
    (root / "pyproject.toml").write_text(
        PYPROJECT + '[project.entry-points."agent_utilities.skill_providers"]\ndemo-mcp = "demo_mcp.skills"\n'
    )
    record = audit.audit_connector(root, _parents(tmp_path))
    assert not record["served"] and not record["pack_complete"]
    assert record["foreign_entry_point_groups"] == ["agent_utilities.skill_providers"]
    assert any(g.startswith("server does not register connector content") for g in record["gaps"])


def test_output_is_deterministic(tmp_path: Path, capsys) -> None:
    root = _connector(tmp_path / "demo-mcp")
    assert audit.main(["--root", str(root)]) == 0
    first = capsys.readouterr().out
    assert audit.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == first
    assert audit.main(["--root", str(root), "--strict"]) == 1  # no parent terms given: classes are orphans
