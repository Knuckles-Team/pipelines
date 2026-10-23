"""connector-ontology-map fix: each codemod rule on fixture packs (PIPE-GATES-R016.6 to R016.9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.hygiene import ontology_codemod as oc
from pipelines_hooks.hygiene import ontology_graph_check as ogc
from pipelines_hooks.hygiene import ontology_orphan_map as omap

HEAD = """@prefix : <http://knuckles.team/kg#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
"""
EG = (
    HEAD
    + """<http://knuckles.team/kg> a owl:Ontology .
:Thing0 a owl:Class ; rdfs:subClassOf owl:Thing .
:File a owl:Class ; rdfs:subClassOf :Thing0 ; rdfs:label "File" .
:Person a owl:Class ; rdfs:subClassOf :Thing0 .
:Server a owl:Class ; rdfs:subClassOf :Thing0 ; rdfs:comment "core server" .
:Category a owl:Class ; rdfs:subClassOf :Thing0 .
"""
)
PACK = (
    HEAD
    + """<http://x/p> a owl:Ontology ;
    rdfs:label "pack" ;
    owl:imports <http://knuckles.team/kg> , <http://other/ont> .
# keep this comment
:Server a owl:Class ;
    rdfs:subClassOf :Thing0 ;
    rdfs:label "Server" ;
    rdfs:comment "dup" ;
    skos:altLabel "box" .
:Persons a owl:Class ; rdfs:label "Persons" .
:Genre a owl:Class .
:TorrentFile a owl:Class .
:Lonely a owl:Class .
:Child a owl:Class ; rdfs:subClassOf :Genre .
:owns a owl:ObjectProperty ; rdfs:range :File .
:links a owl:ObjectProperty .
:refersTo a owl:ObjectProperty ; rdfs:domain :Persn ; rdfs:range :File .
:Persn a owl:Class .
"""
)
SHAPE = HEAD + ":S a sh:NodeShape ; sh:targetClass :Person ; sh:property [ sh:path :owns ; sh:class :File ] ."
MANIFEST = "connector: p\nresources: []\nschema_mappings:\n  Person: {ontology_class: null, fields: {}}\n  Zed: {ontology_class: null, fields: {}}\n"
OVERRIDES = {"*": {"Genre": "Category"}, "p": {"Lonely": None}}


def srcs() -> list[ogc.Source]:
    return [
        ogc.Source("eg:core", "eg", "eg/core.ttl", EG),
        ogc.Source("p", "pack", "p/ontology/p.ttl", PACK),
        ogc.Source("p", "pack", "p/ontology/shapes/s.ttl", SHAPE),
        ogc.Source("p", "pack", "connector_manifest.yml", MANIFEST),
    ]


def patched() -> tuple[dict[str, str], oc.Plan]:
    new, plan = oc.patch_sources(srcs(), OVERRIDES)
    return {s.path: s.text for s in new}, plan


def queue(plan: oc.Plan, rule: str) -> dict[str, dict]:
    return {q["subject"]: q for q in plan.queue if q["rule"] == rule}


@pytest.mark.spec("PIPE-GATES-R016.6")
def test_r1_drops_only_the_eg_import() -> None:
    text = patched()[0]["p/ontology/p.ttl"]
    assert "http://knuckles.team/kg>" not in text.replace("http://knuckles.team/kg#", "")
    assert "http://other/ont" in text and "# keep this comment" in text


@pytest.mark.spec("PIPE-GATES-R016.6")
def test_r2_removes_redeclared_parent_label_comment_keeps_rest() -> None:
    g = ogc.Graph()
    g.parse(data=patched()[0]["p/ontology/p.ttl"], format="turtle")
    server = ogc.URIRef("http://knuckles.team/kg#Server")
    preds = {str(p) for p in g.predicates(server, None)}
    assert not preds & {str(ogc.RDFS.subClassOf), str(ogc.RDFS.label), str(ogc.RDFS.comment)}
    assert "http://www.w3.org/2004/02/skos/core#altLabel" in preds


@pytest.mark.spec("PIPE-GATES-R016.7")
def test_r3_exact_name_singularized_and_r4_override_and_r5_proposal() -> None:
    text, plan = patched()
    g = ogc.Graph()
    g.parse(data=text["p/ontology/p.ttl"], format="turtle")

    def parents(n: str) -> set[str]:
        node = ogc.URIRef(f"http://knuckles.team/kg#{n}")
        return {ogc.local(str(o)) for o in g.objects(node, ogc.RDFS.subClassOf)}

    assert parents("Persons") == {"Person"}
    assert parents("Genre") == {"Category"}
    assert parents("TorrentFile") == set()  # R5 is a proposal only
    assert queue(plan, "R5")["TorrentFile"]["candidates"] == [ogc.KG_NS + "kg#File"]
    assert "Lonely" in queue(plan, "R4") and "audited" in queue(plan, "R4")["Lonely"]["reason"]


@pytest.mark.spec("PIPE-GATES-R016.8")
def test_r6_report_only_never_patches_manifest() -> None:
    text, plan = patched()
    assert text["connector_manifest.yml"] == MANIFEST
    q = queue(plan, "R6")
    assert q["Person"]["candidates"] and not q["Zed"]["candidates"]


@pytest.mark.spec("PIPE-GATES-R016.8")
def test_r7_rewrites_unique_match_and_queues_the_rest() -> None:
    bad = PACK.replace(":Persn a owl:Class .", "") + ":Typo a owl:Class ; rdfs:subClassOf :Persons , :Nothing .\n"
    bad = bad.replace(":Persn", ":Person")
    pk = [
        ogc.Source("eg:core", "eg", "eg/core.ttl", EG),
        ogc.Source("p", "pack", "p/ontology/p.ttl", bad + ":Q a owl:Class ; rdfs:subClassOf :Servers .\n"),
    ]
    new, plan = oc.patch_sources(pk, {})
    assert ":Servers" not in new[1].text and ":Server" in new[1].text
    assert "Nothing" in queue(plan, "R7")


@pytest.mark.spec("PIPE-GATES-R016.9")
def test_r8_infers_only_a_single_candidate() -> None:
    text, plan = patched()
    g = ogc.Graph()
    g.parse(data=text["p/ontology/p.ttl"], format="turtle")
    owns = ogc.URIRef("http://knuckles.team/kg#owns")
    assert [ogc.local(str(o)) for o in g.objects(owns, ogc.RDFS.domain)] == ["Person"]
    assert "links" in queue(plan, "R8")


@pytest.mark.spec("PIPE-GATES-R016.9")
def test_idempotent_deterministic_and_projection() -> None:
    first, _ = oc.patch_sources(srcs(), OVERRIDES)
    again, plan2 = oc.patch_sources([ogc.Source(s.module, s.kind, s.path, s.text) for s in first], OVERRIDES)
    assert [s.text for s in first] == [s.text for s in again]
    one = oc.run_fix(srcs(), [], OVERRIDES)
    two = oc.run_fix(list(reversed(srcs())), [], OVERRIDES)
    assert one["rule_totals"] == two["rule_totals"] and one["patches"] == two["patches"]
    f = one["findings"]
    assert f["after"]["PACK_IMPORTS_CORE"] == 0 < f["before"]["PACK_IMPORTS_CORE"]
    assert f["after"]["NOT_ROLLED_UP_TO_CORE"] < f["before"]["NOT_ROLLED_UP_TO_CORE"]


@pytest.mark.spec("PIPE-GATES-R016.9")
def test_cli_dry_run_writes_patch_summary_and_queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack = tmp_path / "p"
    (pack / "p" / "ontology").mkdir(parents=True)
    (pack / "p" / "ontology" / "p.ttl").write_text(PACK)
    monkeypatch.setattr(ogc, "eg_sources", lambda *a, **k: [ogc.Source("eg:core", "eg", "eg/core.ttl", EG)])
    out = tmp_path / "out"
    assert omap.main(["fix", "--pack", str(pack), "--eg-repo", str(tmp_path), "--dry-run", "--out", str(out)]) == 0
    assert (out / "patches" / "p.patch").read_text().startswith("--- a/p/ontology/p.ttl")
    assert (pack / "p" / "ontology" / "p.ttl").read_text() == PACK  # dry run changes nothing
    assert json.loads((out / "review-queue.json").read_text())["p"]
    assert omap.main(["fix", "--pack", str(pack), "--eg-repo", str(tmp_path), "--out", str(out)]) == 0
    assert "owl:imports <http://knuckles.team/kg>" not in (pack / "p" / "ontology" / "p.ttl").read_text()
