"""connector-ontology-map graph-check: fixture graphs exercise every finding code (PIPE-GATES-R016)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.hygiene import ontology_graph_check as ogc
from pipelines_hooks.hygiene import ontology_orphan_map as omap

pytestmark = pytest.mark.spec("PIPE-GATES-R016")

HEAD = """@prefix : <http://knuckles.team/kg#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""
CORE = (
    HEAD
    + """
:Concept a owl:Class ; rdfs:subClassOf owl:Thing .
:Ticket a owl:Class ; rdfs:subClassOf :Concept ; rdfs:label "Ticket" .
:Server a owl:Class ; rdfs:subClassOf :Ticket .
:Person a owl:Class ; rdfs:subClassOf :Concept .
:assignedTo a owl:ObjectProperty ; rdfs:domain :Ticket ; rdfs:range :Person .
:blank a owl:ObjectProperty .
"""
)
PACK_A = (
    HEAD
    + """
:Issue a owl:Class ; rdfs:label "Issue" .
:Bug a owl:Class ; rdfs:subClassOf :Ticket , :Ghost .
:Server a owl:Class ; rdfs:subClassOf :Concept , :Thing2 .
:Thing2 a owl:Class ; rdfs:subClassOf :Concept .
:Twin1 a owl:Class ; rdfs:label "Twin" ; rdfs:subClassOf :Concept .
:Twin2 a owl:Class ; rdfs:label "Twin" ; rdfs:subClassOf :Concept .
:raisedBy a owl:ObjectProperty ; rdfs:domain :Bug ; rdfs:range :Person .
"""
)
PACK_B = (
    HEAD
    + """
:Defect a owl:Class ; rdfs:label "Issue" ; rdfs:subClassOf :Ghost .
:Server a owl:Class ; rdfs:subClassOf :Person .
"""
)
SHAPE = HEAD + ":S a sh:NodeShape ; sh:targetClass :NoSuchClass ; sh:property [ sh:path :noSuchProp ] ."
MANIFEST = """connector: a
resources:
- name: Bug
  relations:
  - name: nowhere
    target: Missing
schema_mappings:
  Bug: {ontology_class: Bug, fields: {}}
  Other: {ontology_class: null, fields: {}}
  Third: {ontology_class: NotAClass, fields: {}}
"""
INGEST = json.dumps(
    {
        "sources": [
            {"source_id": "s", "record_type": "NoType", "id_field": "id"},
            {"source_id": "t", "record_type": "Bug"},
        ]
    }
)


def sources() -> list[ogc.Source]:
    return [
        ogc.Source("eg:core", "eg", "crates/core.ttl", CORE),
        ogc.Source("packa", "pack", "pa/ontology/a.ttl", PACK_A),
        ogc.Source("packa", "pack", "pa/ontology/shapes/s.ttl", SHAPE),
        ogc.Source("packa", "pack", "connector_manifest.yml", MANIFEST),
        ogc.Source("packa", "pack", "pa/ontology/ingest_sources.json", INGEST),
        ogc.Source("packb", "pack", "pb/ontology/b.ttl", PACK_B),
        ogc.Source("packc", "pack", "pc/ontology/c.ttl", "this is not turtle {"),
        ogc.Source("packd", "pack", "pd/ontology/d.ttl", HEAD + ":Lonely a owl:Class ; rdfs:subClassOf owl:Thing ."),
    ]


QUESTIONS = [
    {
        "id": "Q1",
        "question": "ok",
        "hops": [{"kind": "edge", "from": "Ticket", "property": "assignedTo", "to": "Person"}],
    },
    {
        "id": "Q2",
        "question": "broken",
        "hops": [{"kind": "edge", "from": "Ticket", "property": "missingProp", "to": "Person"}],
    },
    {
        "id": "Q3",
        "question": "pack",
        "hops": [{"kind": "shared_ancestor", "packs": {"packa": "Issue", "packb": "Defect"}}],
    },
]


@pytest.fixture(scope="module")
def result() -> dict:
    return ogc.run(sources(), QUESTIONS)


def codes(result: dict) -> set[str]:
    return {f["code"] for f in result["findings"]}


def test_every_code_is_exercised(result: dict) -> None:
    present = codes(result)
    assert present >= set(ogc.CODES) - {"ISLAND_MODULE"}


def test_parse_error_names_file(result: dict) -> None:
    (f,) = [f for f in result["findings"] if f["code"] == "PARSE_ERROR"]
    assert f["file"] == "pc/ontology/c.ttl" and f["pack"] == "packc"


def test_orphan_reports_chain_length(result: dict) -> None:
    orphans = {f["iri"].rsplit("#", 1)[1]: f for f in result["findings"] if f["code"] == "ORPHAN_CLASS"}
    assert "Issue" in orphans and orphans["Issue"]["detail"]["chain_length"] >= 0
    assert "Ticket" not in orphans


def test_dangling_has_file_and_line(result: dict) -> None:
    dangling = [f for f in result["findings"] if f["code"] == "DANGLING_REFERENCE"]
    names = {f["iri"].rsplit("#", 1)[1] for f in dangling}
    assert {"Ghost", "NoSuchClass", "noSuchProp", "Missing", "nowhere"} <= names
    ghost = next(f for f in dangling if f["iri"].endswith("Ghost") and f["file"].endswith("a.ttl"))
    assert ghost["line"] > 0


def test_untyped_property_and_isolation(result: dict) -> None:
    assert any(f["code"] == "PROPERTY_UNTYPED" and f["iri"].endswith("blank") for f in result["findings"])
    isolated = {f["iri"].rsplit("#", 1)[1] for f in result["findings"] if f["code"] == "ISOLATED_CLASS"}
    assert "Lonely" in isolated


def test_islands_and_components(result: dict) -> None:
    assert result["summary"]["bridging"]["components"] >= 2
    assert any(f["code"] == "ISLAND_PACK" and f["module"] == "packd" for f in result["findings"])


def test_mapping_and_ingest_checks(result: dict) -> None:
    mt = {f["detail"]["type"] for f in result["findings"] if f["code"] == "MAPPING_TARGET_MISSING"}
    assert mt == {"Other", "Third"}
    it = [f for f in result["findings"] if f["code"] == "INGEST_TYPE_MISSING"]
    assert [f["detail"]["record_type"] for f in it] == ["NoType"]
    assert any(f["code"] == "NO_JOIN_KEY" for f in result["findings"])


def test_conflicts(result: dict) -> None:
    cp = [f for f in result["findings"] if f["code"] == "CONFLICTING_PARENT"]
    assert any(f["iri"].endswith("Server") for f in cp)
    assert any(f["code"] == "DUPLICATE_LABEL" and f["module"] == "packa" for f in result["findings"])


def test_competency_questions_name_missing_hops(result: dict) -> None:
    by = {q["id"]: q for q in result["questions"]}
    assert not by["Q3"]["pass"] and "shared ancestor" in by["Q3"]["missing"][0]
    assert by["Q1"]["pass"] and not by["Q2"]["pass"]
    assert "object property missingProp" in by["Q2"]["missing"]
    assert any(f["code"] == "CQ_PATH_BROKEN" and f["detail"]["question"] == "Q2" for f in result["findings"])


def test_fix_plan_is_grouped_by_owner(result: dict) -> None:
    plan = result["fix_plan"]
    assert "epistemic-graph" in plan
    keys = {i["key"] for items in plan.values() for i in items}
    assert "prop:missingProp" in keys
    assert all(i["triples"] for items in plan.values() for i in items)


def test_output_is_deterministic() -> None:
    assert json.dumps(ogc.run(sources(), QUESTIONS), sort_keys=True) == json.dumps(
        ogc.run(sources(), QUESTIONS), sort_keys=True
    )


def test_exit_codes_and_markdown(result: dict) -> None:
    assert ogc.exit_code(result, warn=False) == 1 and ogc.exit_code(result, warn=True) == 0
    clean = ogc.run(
        [
            ogc.Source(
                "eg:core",
                "eg",
                "c.ttl",
                HEAD
                + ":Concept a owl:Class ; rdfs:subClassOf owl:Thing . :name a owl:DatatypeProperty ; rdfs:domain :Concept ; rdfs:range xsd:string .",
            )
        ],
        [],
    )
    assert clean["summary"]["total"] == 0 and ogc.exit_code(clean, warn=False) == 0
    assert "## Findings per code" in ogc.render_markdown(result)


def test_packaged_questions_load() -> None:
    data = json.loads(ogc.DEFAULT_CQ.read_text(encoding="utf-8"))
    assert {q["id"] for q in data["questions"]} >= {"CQ-a", "CQ-b", "CQ-c", "CQ-d1", "CQ-d10"}


def test_cli_graph_check_reads_git_repos(tmp_path: Path) -> None:
    import subprocess

    def git(repo: Path, *a: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True
        )

    eg = tmp_path / "eg"
    (eg / "ontology").mkdir(parents=True)
    (eg / "ontology" / "core-v1.ttl").write_text(
        HEAD
        + ":Concept a owl:Class ; rdfs:subClassOf owl:Thing . :name a owl:DatatypeProperty ; rdfs:domain :Concept ; rdfs:range xsd:string ."
    )
    git(eg, "init", "-q", "-b", "main")
    git(eg, "add", "--", "ontology/core-v1.ttl")
    git(eg, "commit", "-q", "-m", "x")
    (tmp_path / "fleet").mkdir()
    out = tmp_path / "r.json"
    qs = tmp_path / "q.json"
    qs.write_text(json.dumps({"questions": []}))
    argv = [
        "graph-check",
        "--fleet",
        str(tmp_path / "fleet"),
        "--eg-repo",
        str(eg),
        "--ref",
        "HEAD",
        "--questions",
        str(qs),
        "--json",
        str(out),
    ]
    assert omap.main(argv) == 0
    assert json.loads(out.read_text())["summary"]["total"] == 0
