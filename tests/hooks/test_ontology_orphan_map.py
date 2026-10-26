"""connector-ontology-map: propose, review and apply parent classes (PIPE-GATES-R015)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.hygiene import ontology_orphan_map as omap

pytestmark = pytest.mark.spec("PIPE-GATES-R015")  # binds reviewed parent mapping and apply behavior

HEAD = """@prefix : <http://knuckles.team/kg#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
"""

PARENT = (
    HEAD
    + """<http://knuckles.team/kg/core> a owl:Ontology .
:WorkItem a owl:Class ; rdfs:label "Work Item" .
:Document a owl:Class ; rdfs:label "Document" ; skos:altLabel "Paper" .
:Resource a owl:Class .
:Server a owl:Class .
"""
)

CONNECTOR = (
    HEAD
    + """<http://knuckles.team/kg/demo> a owl:Ontology .
:Issue a owl:Class ; rdfs:label "Issue" ; rdfs:comment "A tracked defect." .
:Paper a owl:Class ; rdfs:label "Paper" .
:GitLabDocument a owl:Class ; rdfs:label "GitLab Document" .
:Gadget a owl:Class ; rdfs:label "Gadget" .
:SubGadget a owl:Class ; rdfs:subClassOf :Gadget .
:Server a owl:Class .
:Wrapper a owl:Class ; rdfs:comment "Wraps a :Document for transport." .
"""
)


@pytest.fixture
def parent(tmp_path: Path) -> omap.Parent:
    (tmp_path / "core.ttl").write_text(PARENT)
    return omap.load_parent(tmp_path)


def _by_class(result: dict) -> dict[str, dict]:
    return {omap.local_name(p["class"]): p for p in result["proposals"]}


def test_signals_and_confidence(parent: omap.Parent) -> None:
    result = omap.propose_file(CONNECTOR, parent)
    found = _by_class(result)
    assert result["orphans"] == 6  # :Server is a parent term, not an orphan
    assert found["Paper"]["proposed_parent"].endswith("#Document") and found["Paper"]["auto"]  # alias is exact
    assert found["GitLabDocument"]["proposed_parent"].endswith("#Document")
    assert not found["GitLabDocument"]["auto"] and found["GitLabDocument"]["confidence"] < 1
    assert found["Issue"]["proposed_parent"].endswith("#WorkItem") and not found["Issue"]["auto"]  # synonym
    assert found["Wrapper"]["proposed_parent"].endswith("#Document") and "comment" in found["Wrapper"]["reasons"][0]
    assert all(p["reasons"] for p in found.values())


def test_a_subclass_of_an_orphan_is_resolved_by_its_root(parent: omap.Parent) -> None:
    found = _by_class(omap.propose_file(CONNECTOR, parent))
    assert "SubGadget" not in found
    assert found["Gadget"]["subclasses_resolved"] == ["http://knuckles.team/kg#SubGadget"]


def test_no_signal_is_a_new_parent_candidate_and_nothing_is_invented(parent: omap.Parent) -> None:
    found = _by_class(omap.propose_file(CONNECTOR, parent))
    assert found["Gadget"]["proposed_parent"] is None and found["Gadget"]["confidence"] == 0.0
    # the synonym table sends "fan" to "Device"; the fixture parent has none, so nothing may be proposed
    fan = omap.propose_file(HEAD + ":Fan a owl:Class .\n", parent)
    assert fan["proposals"][0]["proposed_parent"] is None


def test_exact_match_on_a_generic_class_is_not_automatic(parent: omap.Parent) -> None:
    text = HEAD + "@prefix d: <http://example.org/d#> .\nd:Resource a owl:Class .\n"
    proposal = omap.propose_file(text, parent)["proposals"][0]
    assert proposal["proposed_parent"].endswith("#Resource") and not proposal["auto"]


def test_decide_accepts_overrides_and_rejects_an_invented_parent(parent: omap.Parent) -> None:
    record = {"repository": "demo", "files": {"demo/ontology/d.ttl": omap.propose_file(CONNECTOR, parent)}}
    decided = omap.decide(record, {"Gadget": "Server", "Wrapper": None}, parent)
    links = decided["links"]["demo/ontology/d.ttl"]
    assert links["http://knuckles.team/kg#Gadget"] == "http://knuckles.team/kg#Server"
    assert "http://knuckles.team/kg#Wrapper" not in links
    assert [c["class"] for c in decided["new_parent_candidates"]] == [
        "http://knuckles.team/kg#GitLabDocument",
        "http://knuckles.team/kg#Issue",
        "http://knuckles.team/kg#Wrapper",
    ]
    with pytest.raises(ValueError, match="not in the parent ontology"):
        omap.decide(record, {"Gadget": "Widget"}, parent)


def test_non_exact_and_generic_proposals_need_explicit_review(parent: omap.Parent) -> None:
    record = {"repository": "demo", "files": {"demo/ontology/d.ttl": omap.propose_file(CONNECTOR, parent)}}
    rejected = omap.decide(record, {}, parent)
    assert rejected["links"] == {
        "demo/ontology/d.ttl": {
            "http://knuckles.team/kg#Paper": "http://knuckles.team/kg#Document",
        }
    }

    reviewed = omap.decide(
        record,
        {"GitLabDocument": "Document", "Issue": "WorkItem", "Wrapper": "Document"},
        parent,
    )
    links = reviewed["links"]["demo/ontology/d.ttl"]
    assert links["http://knuckles.team/kg#GitLabDocument"].endswith("#Document")
    assert links["http://knuckles.team/kg#Issue"].endswith("#WorkItem")
    assert links["http://knuckles.team/kg#Wrapper"].endswith("#Document")

    generic_text = HEAD + "@prefix d: <http://example.org/d#> .\nd:Resource a owl:Class .\n"
    generic_record = {"repository": "demo", "files": {"demo/ontology/d.ttl": omap.propose_file(generic_text, parent)}}
    generic = omap.decide(generic_record, {}, parent)
    assert generic["links"] == {}
    explicit_generic = omap.decide(generic_record, {"Resource": "Resource"}, parent)
    assert explicit_generic["links"]["demo/ontology/d.ttl"]


def test_bfo_exact_proposal_needs_explicit_review(parent: omap.Parent) -> None:
    bfo = "http://purl.obolibrary.org/obo/BFO_0000040"
    parent.classes[bfo] = {"names": {"BFO_0000040"}, "supers": set()}
    parent.by_key.setdefault(omap.key("BFO_0000040"), []).append(bfo)
    parent.by_local.setdefault("BFO_0000040", []).append(bfo)
    text = HEAD + "@prefix d: <http://example.org/d#> .\nd:BFO_0000040 a owl:Class .\n"
    record = {"repository": "demo", "files": {"demo/ontology/d.ttl": omap.propose_file(text, parent)}}
    proposal = record["files"]["demo/ontology/d.ttl"]["proposals"][0]
    assert proposal["confidence"] >= omap.ACCEPT_AT and not proposal["auto"]
    assert omap.decide(record, {}, parent)["links"] == {}
    assert omap.decide(record, {"BFO_0000040": "BFO_0000040"}, parent)["links"]


def test_apply_writes_links_and_the_import_and_nothing_else() -> None:
    text = (
        HEAD
        + '<http://knuckles.team/kg/demo> a owl:Ontology ; rdfs:label "Demo" .\n\n# keep me\n:Gadget a owl:Class ;\n    rdfs:label "Gadget" .\n:Plain a owl:Class .\n'
    )
    new, problems = omap.apply_links(
        text,
        {
            "http://knuckles.team/kg#Gadget": "http://knuckles.team/kg#Server",
            "http://knuckles.team/kg#Plain": "http://knuckles.team/kg#Server",
        },
    )
    assert problems == []
    doc = omap.parse(new)
    assert doc.objects("http://knuckles.team/kg#Gadget", omap._SUBCLASS) == {"http://knuckles.team/kg#Server"}
    assert doc.objects("http://knuckles.team/kg#Plain", omap._SUBCLASS) == {"http://knuckles.team/kg#Server"}
    assert doc.objects(None, omap._OWL + "imports") == {omap.PARENT_IRI}
    assert "# keep me" in new and 'rdfs:label "Demo"' in new
    again, _ = omap.apply_links(new, {})
    assert again == new  # the import is already there


def test_apply_reports_a_class_it_cannot_find() -> None:
    _, problems = omap.apply_links(
        HEAD + "<http://x/o> a owl:Ontology .\n", {"http://knuckles.team/kg#Nope": "http://knuckles.team/kg#Server"}
    )
    assert any("Nope" in p for p in problems)


def test_apply_makes_the_audit_see_no_orphans(parent: omap.Parent) -> None:
    from pipelines_hooks.hygiene import connector_surface as audit

    record = {"repository": "demo", "files": {"f.ttl": omap.propose_file(CONNECTOR, parent)}}
    links = omap.decide(record, {"Gadget": "Server", "Wrapper": "Document"}, parent)["links"]["f.ttl"]
    new, problems = omap.apply_links(CONNECTOR, links)
    assert problems == []
    directory = Path(__import__("tempfile").mkdtemp(dir=Path(__file__).parent))
    try:
        (directory / "p.ttl").write_text(PARENT)
        report = audit.ontology_report(_write(directory, new), directory, audit.parent_terms(directory))
    finally:
        for child in directory.iterdir():
            child.unlink()
        directory.rmdir()
    assert report["orphans"] == [] and report["imports_parent"]


def _write(directory: Path, text: str) -> Path:
    path = directory / "c.ttl"
    path.write_text(text)
    return path


def test_output_is_deterministic_and_propose_cli_writes_json(tmp_path: Path, parent: omap.Parent) -> None:
    assert json.dumps(omap.propose_file(CONNECTOR, parent), sort_keys=True) == json.dumps(
        omap.propose_file(CONNECTOR, parent), sort_keys=True
    )


def test_scaffold_writes_a_test_that_passes_and_names_pending_classes(tmp_path: Path, parent: omap.Parent) -> None:
    root = tmp_path / "conn"
    ontology = root / "demo_mcp" / "ontology"
    ontology.mkdir(parents=True)
    linked, problems = omap.apply_links(
        CONNECTOR, {"http://knuckles.team/kg#Issue": "http://knuckles.team/kg#WorkItem"}
    )
    assert problems == []
    (ontology / "demo.ttl").write_text(linked)
    pending = {"demo_mcp/ontology/demo.ttl": ["http://knuckles.team/kg#Gadget", "http://knuckles.team/kg#SubGadget"]}
    written = omap.scaffold_test(root, "CONN-DEMO-R002", {}, pending, parent)
    source = written.read_text()
    namespace: dict = {"__file__": str(written), "__name__": "scaffolded"}
    # The pytest.mark.spec marker is unknown here; the module body must still run and its test pass or fail on content.
    exec(
        compile(source.replace("pytestmark = pytest.mark.spec", "pytestmark = (lambda *a: a)"), str(written), "exec"),
        namespace,
    )
    assert namespace["PENDING_NEW_PARENT"] == frozenset(
        {"http://knuckles.team/kg#Gadget", "http://knuckles.team/kg#SubGadget"}
    )
    triples = namespace["_triples"](linked)
    # Paper, GitLabDocument and Wrapper remain orphans here, so the generated test would fail on this file.
    assert "http://knuckles.team/kg#Paper" in namespace["_orphans"](triples)
