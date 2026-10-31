"""connector-ontology-map graph-check: validate that every ontology is reachable and bridged.

``graph-check`` composes the epistemic-graph (EG) ontology modules and every fleet
connector pack (``<pkg>/ontology/*.ttl``, shapes, the generated ``connector_sources.py`` declaration) into one rdflib graph and reports findings, each with a
machine-readable code (PIPE-GATES-R016):

* ``PARSE_ERROR``: a Turtle file or the declaration does not parse.
* ``PACK_IMPORTS_CORE``: a pack ``owl:imports`` an EG ontology (an antipattern, not a bridge).
* ``NOT_ROLLED_UP_TO_CORE``: a pack class never reaches a class declared in an EG module.
* ``ORPHAN_CLASS`` (EG modules only): a class has no ``subClassOf``/``equivalentClass``/intersection path to the root.
* ``ISLAND_MODULE`` / ``ISLAND_PACK``: a module or pack is outside the main connected component.
* ``DANGLING_REFERENCE``: an IRI is used as a parent, domain, range, property, shape target or
  mapping target but declared nowhere.
* ``PROPERTY_UNTYPED``: an object property lacks a domain or a range.
* ``ISOLATED_CLASS``: a class has no object-property edge to a class outside its own pack.
* ``UNBRIDGED_SAME_CONCEPT``: one concept name in two or more packs without a shared non-generic ancestor.
* ``INGEST_TYPE_MISSING`` / ``MAPPING_TARGET_MISSING`` / ``NO_JOIN_KEY``: virtual graph and data checks.
* ``CONFLICTING_PARENT`` / ``DUPLICATE_LABEL``: conflicting declarations.
* ``CQ_PATH_BROKEN``: a competency question needs a class path the composed graph lacks.

The result is deterministic: sorted findings, no timestamps.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

KG_NS = "http://knuckles.team/"
SH = "http://www.w3.org/ns/shacl#"
BFO_ROOT = "http://purl.obolibrary.org/obo/BFO_0000001"
ROOTS = {str(OWL.Thing), BFO_ROOT, str(RDFS.Resource)}
OWL_NS = "http://www.w3.org/2002/07/owl#"
CLASS_TYPES = {OWL.Class, RDFS.Class}
PROP_TYPES = {
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    RDF.Property,
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
}
SKOS_ALT = URIRef("http://www.w3.org/2004/02/skos/core#altLabel")
SKOS_PREF = URIRef("http://www.w3.org/2004/02/skos/core#prefLabel")
# Ancestors too broad to count as a shared concept (the generic core).
GENERIC = {
    "concept",
    "resource",
    "entity",
    "thing",
    "item",
    "object",
    "record",
    "node",
    "element",
    "type",
    "instance",
    "artifact",
    "continuant",
    "occurrent",
    "agent",
    "document",
}
CODES = (
    "PARSE_ERROR",
    "ORPHAN_CLASS",
    "ISLAND_MODULE",
    "ISLAND_PACK",
    "DANGLING_REFERENCE",
    "PROPERTY_UNTYPED",
    "ISOLATED_CLASS",
    "UNBRIDGED_SAME_CONCEPT",
    "INGEST_TYPE_MISSING",
    "MAPPING_TARGET_MISSING",
    "NO_JOIN_KEY",
    "CONFLICTING_PARENT",
    "DUPLICATE_LABEL",
    "CQ_PATH_BROKEN",
    "PACK_IMPORTS_CORE",
    "NOT_ROLLED_UP_TO_CORE",
)
EG_CATALOG_IRI = "http://knuckles.team/kg"
DEFAULT_CQ = Path(__file__).with_name("ontology_cqs.json")


def local(iri: str) -> str:
    return re.split(r"[#/]", iri.rstrip("#/"))[-1]


def _checkable(iri: str) -> bool:
    return iri.startswith(KG_NS)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _tokens(name: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)]


@dataclass
class Source:
    """One input file: its module, its text (for line lookup) and its parsed graph."""

    module: str
    kind: str  # "eg" or "pack"
    path: str
    text: str
    graph: Graph | None = None


@dataclass
class Finding:
    code: str
    message: str
    module: str = ""
    pack: str = ""
    file: str = ""
    line: int = 0
    iri: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message, "module": self.module, "pack": self.pack}
        if self.file:
            out["file"] = self.file
        if self.line:
            out["line"] = self.line
        if self.iri:
            out["iri"] = self.iri
        if self.detail:
            out["detail"] = self.detail
        return out


# -- loading -------------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # a hook exports GIT_DIR
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False, env=env)
    return done.stdout if done.returncode == 0 else ""


FIXTURE_DIR_SUFFIXES = ("fixture", "fixtures")


def is_fixture_path(path: str) -> bool:
    """Path rule: a file under any directory whose name ends in ``fixture`` or ``fixtures`` is test data, not corpus."""
    return any(d.endswith(FIXTURE_DIR_SUFFIXES) for d in path.split("/")[:-1])


def eg_sources(repo: Path, ref: str, overlay: str | None = None) -> list[Source]:
    """Every ``*.ttl`` of the EG repo at ``ref``; with ``overlay``, the files that ref changed replace the base."""
    paths = {
        p: ref
        for p in _git(repo, "ls-tree", "-r", "--name-only", ref).splitlines()
        if p.endswith(".ttl") and not is_fixture_path(p)
    }
    if overlay:
        base = _git(repo, "merge-base", ref, overlay).strip() or ref
        for line in _git(repo, "diff", "--name-status", base, overlay).splitlines():
            status, _, path = line.partition("\t")
            if path.endswith(".ttl") and not is_fixture_path(path):
                if status.startswith("D"):
                    paths.pop(path, None)
                else:
                    paths[path] = overlay
    return [
        Source(module="eg:" + Path(p).name.removesuffix(".ttl"), kind="eg", path=p, text=_git(repo, "show", f"{r}:{p}"))
        for p, r in sorted(paths.items())
    ]


DECLARATION = "connector_sources.py"


def parse_declaration(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Statically read ``connector_sources.py``: the ``source_meta(...)`` entries, schema mappings and resources.

    The module is parsed by AST and never imported; only literal keyword values are read.
    """
    tree = ast.parse(text)
    entries: list[dict[str, Any]] = []
    declared: dict[str, Any] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and (getattr(node.func, "id", None) or getattr(node.func, "attr", None)) == "source_meta"
        ):
            entry: dict[str, Any] = {}
            for kw in node.keywords:
                if kw.arg:
                    try:
                        entry[kw.arg] = ast.literal_eval(kw.value)
                    except ValueError:
                        entry[kw.arg] = None
            entries.append(entry)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("SCHEMA_MAPPINGS", "RESOURCES", "CONNECTOR"):
                declared[node.targets[0].id] = ast.literal_eval(node.value)
    body = {"schema_mappings": declared.get("SCHEMA_MAPPINGS") or {}, "resources": declared.get("RESOURCES") or {}}
    if isinstance(body["resources"], dict):  # a name -> spec mapping; the checks read a list of named specs
        body["resources"] = [{"name": k, **(v if isinstance(v, dict) else {})} for k, v in body["resources"].items()]
    return entries, body


def pack_sources(repo: Path, ref: str) -> list[Source]:
    out = []
    for p in sorted(_git(repo, "ls-tree", "-r", "--name-only", ref).splitlines()):
        if is_fixture_path(p):
            continue
        if ("/ontology/" in p and p.endswith(".ttl")) or p.endswith("/" + DECLARATION):
            text = _git(repo, "show", f"{ref}:{p}")
            out.append(Source(module=repo.name, kind="pack", path=p, text=text))
    return out


def fleet_sources(fleet: Path, ref: str, exclude: list[str]) -> list[Source]:
    out = []
    for repo in sorted(r for r in fleet.iterdir() if (r / ".git").exists() and r.name not in set(exclude)):
        out.extend(pack_sources(repo, ref))
    return out


# -- composition ---------------------------------------------------------------------------


@dataclass
class Model:
    sources: list[Source]
    composed: Graph = field(default_factory=Graph)
    findings: list[Finding] = field(default_factory=list)
    class_mods: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    prop_mods: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    obj_props: set[str] = field(default_factory=set)
    parents: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    mod_parents: dict[tuple[str, str], set[str]] = field(default_factory=lambda: defaultdict(set))
    labels: dict[str, dict[str, set[str]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(set)))
    main_labels: dict[str, dict[str, set[str]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(set)))
    domains: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    ranges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    imports: list[tuple[str, str]] = field(default_factory=list)  # importing module, imported ontology IRI
    import_refs: list[tuple[str, str, str]] = field(default_factory=list)  # module, file, imported ontology IRI
    ontology_mods: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))  # ontology IRI -> modules
    type_refs: list[tuple[str, str]] = field(default_factory=list)  # class IRI typed by an individual, module
    refs: list[tuple[str, str, str, str]] = field(default_factory=list)  # iri, role, module, file
    manifests: dict[str, dict[str, Any]] = field(default_factory=dict)
    ingest: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    kind: dict[str, str] = field(default_factory=dict)
    _anc: dict[str, set[str]] = field(default_factory=dict)

    # accessors
    def declared_class(self, iri: str) -> bool:
        return iri in self.class_mods

    def declared_prop(self, iri: str) -> bool:
        return iri in self.prop_mods

    def ancestors(self, iri: str) -> set[str]:
        if iri in self._anc:
            return self._anc[iri]
        seen: set[str] = set()
        todo = [iri]
        while todo:
            for p in self.parents.get(todo.pop(), ()):
                if p not in seen and p != iri:
                    seen.add(p)
                    todo.append(p)
        self._anc[iri] = seen
        return seen

    def find_class(self, name: str, pack: str | None = None) -> str | None:
        """Resolve a local name (or full IRI) to a declared class, preferring ``pack``."""
        if name.startswith("http"):
            return name if name in self.class_mods else None
        hits = sorted(i for i in self.class_mods if local(i) == name and _checkable(i))
        if pack:
            own = [i for i in hits if pack in self.class_mods[i]]
            if own:
                return own[0]
        return hits[0] if hits else None

    def find_prop(self, name: str) -> str | None:
        hits = sorted(i for i in self.prop_mods if local(i) == name and _checkable(i))
        return hits[0] if hits else None


def _members(g: Graph, node: Any, depth: int = 0) -> list[str]:
    """URIRefs in a domain/range expression (a class, or a union/intersection of classes)."""
    if isinstance(node, URIRef):
        return [str(node)]
    out: list[str] = []
    if depth > 4:
        return out
    for pred in (OWL.unionOf, OWL.intersectionOf):
        for lst in g.objects(node, pred):
            for item in Collection(g, lst):
                out.extend(_members(g, item, depth + 1))
    return out


def _line_of(source: Source, iri: str) -> int:
    name = re.escape(local(iri))
    pat = re.compile(r"(?:[:/#]|<[^>]*[#/])" + name + r"(?![\w-])" + r"|\b" + name + r"\b")
    for n, line in enumerate(source.text.splitlines(), 1):
        if pat.search(line):
            return n
    return 0


def compose(sources: list[Source]) -> Model:
    m = Model(sources=sources)
    by_file: dict[tuple[str, str], Source] = {}
    for s in sources:
        m.kind[s.module] = s.kind
        by_file[(s.module, s.path)] = s
        try:
            if s.path.endswith(".ttl"):
                s.graph = Graph()
                s.graph.parse(data=s.text, format="turtle")
            elif s.path.endswith(DECLARATION):
                entries, body = parse_declaration(s.text)
                m.ingest.setdefault(s.module, []).extend(entries)
                m.manifests[s.module] = body
        except Exception as exc:  # noqa: BLE001 - every parse failure is a finding
            s.graph = None
            m.findings.append(
                Finding("PARSE_ERROR", f"{s.path} does not parse: {str(exc)[:200]}", s.module, s.module, s.path)
            )
    for s in sources:
        if s.graph is None:
            continue
        m.composed += s.graph
        g = s.graph
        mod = s.module
        for subj, _, typ in g.triples((None, RDF.type, None)):
            if not isinstance(subj, URIRef):
                continue
            if typ == OWL.Ontology:
                m.ontology_mods[str(subj)].add(mod)
            elif typ in CLASS_TYPES:
                m.class_mods[str(subj)].add(mod)
            elif typ in PROP_TYPES:
                m.prop_mods[str(subj)].add(mod)
                if typ == OWL.ObjectProperty:
                    m.obj_props.add(str(subj))
        for _, _, obj in g.triples((None, OWL.imports, None)):
            if isinstance(obj, URIRef):
                m.imports.append((mod, str(obj)))
                m.import_refs.append((mod, s.path, str(obj)))
        for subj, _, typ in g.triples((None, RDF.type, None)):
            if isinstance(subj, URIRef) and isinstance(typ, URIRef) and not str(typ).startswith(OWL_NS):
                m.type_refs.append((str(typ), mod))
        for subj, pred, obj in g:
            if not isinstance(subj, URIRef):
                continue
            sid = str(subj)
            if pred in (RDFS.label, SKOS_PREF, SKOS_ALT) and isinstance(obj, Literal):
                m.labels[sid][mod].add(str(obj))
                if pred == RDFS.label:
                    m.main_labels[sid][mod].add(str(obj))
            elif pred == RDFS.subClassOf:
                m.refs.append((sid, "class", mod, s.path))
                for p in _members(g, obj):
                    m.parents[sid].add(p)
                    m.mod_parents[(sid, mod)].add(p)
                    m.refs.append((p, "class", mod, s.path))
            elif pred == OWL.equivalentClass:
                m.refs.append((sid, "class", mod, s.path))
                for p in _members(g, obj):
                    m.parents[sid].add(p)
                    m.parents[p].add(sid)
                    m.refs.append((p, "class", mod, s.path))
            elif pred == RDFS.domain:
                m.refs.append((sid, "property", mod, s.path))
                for p in _members(g, obj):
                    m.domains[sid].add(p)
                    m.refs.append((p, "class", mod, s.path))
            elif pred == RDFS.range:
                m.refs.append((sid, "property", mod, s.path))
                for p in _members(g, obj):
                    m.ranges[sid].add(p)
                    m.refs.append((p, "class", mod, s.path))
            elif pred in (RDFS.subPropertyOf, OWL.inverseOf) and isinstance(obj, URIRef):
                m.refs.append((str(obj), "property", mod, s.path))
            elif str(pred) == SH + "targetClass" and isinstance(obj, URIRef):
                m.refs.append((str(obj), "class", mod, s.path))
        for bn in g.subjects(RDF.type, OWL.Class):
            if isinstance(bn, BNode):  # anonymous intersection class used as an equivalent expression
                pass
        for pred_iri in (SH + "path",):
            for _, _, obj in g.triples((None, URIRef(pred_iri), None)):
                if isinstance(obj, URIRef):
                    m.refs.append((str(obj), "property", mod, s.path))
        for pred_iri in (SH + "class",):
            for _, _, obj in g.triples((None, URIRef(pred_iri), None)):
                if isinstance(obj, URIRef):
                    m.refs.append((str(obj), "class", mod, s.path))
        # blank-node intersection parents of a named class: owl:equivalentClass [ owl:intersectionOf (...) ]
    # blank-node declared classes (equivalentClass with restriction) never count as declarations.
    return m


# -- checks --------------------------------------------------------------------------------


def _module_of(m: Model, iri: str) -> str:
    return sorted(m.class_mods.get(iri) or m.prop_mods.get(iri) or [""])[0]


def _file_for(m: Model, module: str, iri: str) -> tuple[str, int]:
    for s in m.sources:
        if s.module == module and s.path.endswith(".ttl") and local(iri) in s.text:
            return s.path, _line_of(s, iri)
    return "", 0


def _pack_of(m: Model, module: str) -> str:
    return module if m.kind.get(module) == "pack" else "eg"


def _eg_declared(m: Model, iri: str) -> bool:
    return any(m.kind.get(x) == "eg" for x in m.class_mods.get(iri, ()))


def _is_eg_import(m: Model, onto: str) -> bool:
    if onto.rstrip("#/") == EG_CATALOG_IRI:
        return True
    return any(m.kind.get(x) == "eg" for x in m.ontology_mods.get(onto, ()))


def check_pack_imports(m: Model) -> None:
    """PACK_IMPORTS_CORE: a pack importing an EG ontology is an antipattern, never a bridge."""
    by_path = {(s.module, s.path): s for s in m.sources}
    for mod, path, onto in sorted(set(m.import_refs)):
        if m.kind.get(mod) == "pack" and _is_eg_import(m, onto):
            m.findings.append(
                Finding(
                    "PACK_IMPORTS_CORE",
                    f"{mod} imports the EG ontology <{onto}>; a pack extends EG classes and never imports it",
                    mod,
                    mod,
                    path,
                    _line_of(by_path[(mod, path)], "imports") if (mod, path) in by_path else 0,
                    onto,
                )
            )


def check_rollup(m: Model) -> None:
    """NOT_ROLLED_UP_TO_CORE: a pack class whose parent chain never reaches a class declared in an EG module."""
    for iri in sorted(m.class_mods):
        if not _checkable(iri) or _eg_declared(m, iri):
            continue
        if any(_eg_declared(m, a) for a in m.ancestors(iri)):
            continue
        mod = _module_of(m, iri)
        f, ln = _file_for(m, mod, iri)
        top = sorted(a for a in m.ancestors(iri) if _checkable(a))
        m.findings.append(
            Finding(
                "NOT_ROLLED_UP_TO_CORE",
                f"{local(iri)} never reaches an EG core class through subClassOf/equivalentClass",
                mod,
                _pack_of(m, mod),
                f,
                ln,
                iri,
                {"ancestors": [local(a) for a in top]},
            )
        )


def check_orphans(m: Model) -> None:
    for iri in sorted(m.class_mods):
        if not _checkable(iri) or not _eg_declared(m, iri):
            continue
        seen = {iri: 0}
        todo = [iri]
        reached: tuple[str, int] | None = None
        top = (iri, 0)
        while todo and reached is None:
            cur = todo.pop(0)
            for p in sorted(m.parents.get(cur, ())):
                if p in seen:
                    continue
                seen[p] = seen[cur] + 1
                if p in ROOTS:
                    reached = ("root", seen[p])
                    break
                if not _checkable(p) and p not in m.class_mods:
                    reached = ("external", seen[p])  # a standard vocabulary class (skos, time, prov, ...)
                    break
                todo.append(p)
                if seen[p] > top[1]:
                    top = (p, seen[p])
        if reached is None:
            mod = _module_of(m, iri)
            f, ln = _file_for(m, mod, iri)
            m.findings.append(
                Finding(
                    "ORPHAN_CLASS",
                    f"{local(iri)} has no path to the upper root; the chain ends at {local(top[0])} after {top[1]} step(s)",
                    mod,
                    _pack_of(m, mod),
                    f,
                    ln,
                    iri,
                    {"chain_length": top[1], "chain_top": top[0]},
                )
            )


def check_dangling(m: Model) -> None:
    seen: set[tuple[str, str, str]] = set()
    by_path = {(s.module, s.path): s for s in m.sources}
    for iri, role, mod, path in m.refs:
        if not _checkable(iri) or (iri, mod, path) in seen:
            continue
        ok = m.declared_class(iri) if role == "class" else m.declared_prop(iri)
        if role == "class" and not ok and m.declared_prop(iri):
            ok = True
        if ok:
            continue
        seen.add((iri, mod, path))
        m.findings.append(
            Finding(
                "DANGLING_REFERENCE",
                f"{local(iri)} is used as a {role} but declared nowhere",
                mod,
                _pack_of(m, mod),
                path,
                _line_of(by_path[(mod, path)], iri),
                iri,
                {"role": role},
            )
        )
    # manifest relations and mapping targets reference classes and properties by name
    for pack, man in sorted(m.manifests.items()):
        for res in man.get("resources") or []:
            for rel in res.get("relations") or []:
                tgt = rel.get("target")
                if tgt and not m.find_class(tgt):
                    m.findings.append(
                        Finding(
                            "DANGLING_REFERENCE",
                            f"manifest relation {res.get('name')}.{rel.get('name')} targets undeclared class {tgt}",
                            pack,
                            pack,
                            DECLARATION,
                            0,
                            KG_NS + "kg#" + tgt,
                            {"role": "class", "source": "manifest_relation", "owner_type": res.get("name")},
                        )
                    )
                if rel.get("name") and not m.find_prop(rel["name"]):
                    m.findings.append(
                        Finding(
                            "DANGLING_REFERENCE",
                            f"manifest relation {res.get('name')}.{rel['name']} names an undeclared property",
                            pack,
                            pack,
                            DECLARATION,
                            0,
                            KG_NS + "kg#" + rel["name"],
                            {
                                "role": "property",
                                "source": "manifest_relation",
                                "domain": res.get("name"),
                                "range": tgt,
                            },
                        )
                    )


def check_properties(m: Model) -> None:
    for p in sorted(m.obj_props):
        if not _checkable(p):
            continue
        miss = [side for side, d in (("domain", m.domains), ("range", m.ranges)) if not d.get(p)]
        if miss:
            mod = _module_of(m, p)
            f, ln = _file_for(m, mod, p)
            m.findings.append(
                Finding(
                    "PROPERTY_UNTYPED",
                    f"object property {local(p)} lacks {' and '.join(miss)}",
                    mod,
                    _pack_of(m, mod),
                    f,
                    ln,
                    p,
                    {"missing": miss},
                )
            )


def _packs_of(m: Model, iri: str) -> set[str]:
    return {_pack_of(m, x) for x in m.class_mods.get(iri, ())}


def check_isolated(m: Model) -> list[str]:
    """ISOLATED_CLASS findings; returns the data-only classes (listed, allowed)."""
    other: dict[str, set[str]] = defaultdict(set)  # class -> other-end classes via object properties
    props_of: dict[str, set[str]] = defaultdict(set)  # class -> object properties touching it
    dt_domain: set[str] = set()
    for p in m.obj_props:
        ds, rs = m.domains.get(p, set()), m.ranges.get(p, set())
        for c in ds | rs:
            props_of[c].add(p)
        for d in ds:
            other[d] |= rs
        for r in rs:
            other[r] |= ds
    for p in m.prop_mods:
        if p not in m.obj_props:
            dt_domain |= m.domains.get(p, set())
    pack_cache = {i: _packs_of(m, i) for i in m.class_mods}
    data_only: list[str] = []
    for iri in sorted(m.class_mods):
        if not _checkable(iri):
            continue
        own = pack_cache[iri]
        cross = any(pack_cache.get(o, set()) ^ own for o in other.get(iri, ()))
        # an edge also counts when the property is declared by a different pack than the class
        cross = cross or any({_pack_of(m, x) for x in m.prop_mods.get(p, ())} - own for p in props_of.get(iri, ()))
        if cross:
            continue
        has_any = bool(props_of.get(iri))
        if iri in dt_domain and not has_any:
            data_only.append(iri)
            continue
        mod = _module_of(m, iri)
        f, ln = _file_for(m, mod, iri)
        m.findings.append(
            Finding(
                "ISOLATED_CLASS",
                f"{local(iri)} has no object-property edge to a class outside {'/'.join(sorted(own))}",
                mod,
                _pack_of(m, mod),
                f,
                ln,
                iri,
                {"has_in_pack_edge": has_any},
            )
        )
    return data_only


def _useful_ancestors(m: Model, iri: str) -> set[str]:
    return {
        a
        for a in m.ancestors(iri)
        if _checkable(a)
        and a in m.class_mods
        and _tokens(local(a))[-1:] != []
        and local(a).lower() not in GENERIC
        and not (m.class_mods[a] <= {x for x in m.class_mods[a] if x == "eg:core-foundation-v1"})
    }


def check_same_concept(m: Model) -> None:
    groups: dict[str, set[str]] = defaultdict(set)
    for iri in m.class_mods:
        if not _checkable(iri):
            continue
        keys = {_norm(local(iri))}
        for per_mod in m.labels.get(iri, {}).values():
            keys |= {_norm(x) for x in per_mod}
        for k in keys:
            if k:
                groups[k].add(iri)
    done: set[frozenset[str]] = set()
    for key, iris in sorted(groups.items()):
        if len(iris) < 2:
            continue
        packs = {i: _packs_of(m, i) for i in iris}
        allpacks = set().union(*packs.values())
        if len(allpacks) < 2:
            continue
        fs = frozenset(iris)
        if fs in done:
            continue
        done.add(fs)
        shared = None
        for i in sorted(iris):
            for j in sorted(iris):
                if i < j and ((_useful_ancestors(m, i) | {i}) & (_useful_ancestors(m, j) | {j})):
                    shared = True
        anc = [_useful_ancestors(m, i) | {i} for i in sorted(iris)]
        common = set.intersection(*anc)
        if common:
            continue
        if shared and all(
            any((a & b) for b in anc if b is not a) for a in anc
        ):  # pairwise chain bridged through different ancestors
            continue
        mod = _module_of(m, sorted(iris)[0])
        m.findings.append(
            Finding(
                "UNBRIDGED_SAME_CONCEPT",
                f"concept '{key}' appears as {len(iris)} classes in {len(allpacks)} packs with no shared ancestor below the core",
                mod,
                _pack_of(m, mod),
                "",
                0,
                sorted(iris)[0],
                {"key": key, "classes": sorted(iris), "packs": sorted(allpacks)},
            )
        )


def check_conflicts(m: Model) -> None:
    by_class: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for (iri, mod), ps in m.mod_parents.items():
        if mod in m.class_mods.get(iri, ()) and ps and _checkable(iri):
            by_class[iri][mod] = ps
    for iri, per in sorted(by_class.items()):
        mods = sorted(per)
        for i, a in enumerate(mods):
            for b in mods[i + 1 :]:
                if (
                    not (per[a] & per[b])
                    and not (m.ancestors(next(iter(per[a]))) & per[b])
                    and not (m.ancestors(next(iter(per[b]))) & per[a])
                ):
                    m.findings.append(
                        Finding(
                            "CONFLICTING_PARENT",
                            f"{local(iri)} has different parents in {a} and {b}",
                            a,
                            _pack_of(m, a),
                            "",
                            0,
                            iri,
                            {"parents": {a: sorted(per[a]), b: sorted(per[b])}},
                        )
                    )
    by_mod: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for iri, per in m.main_labels.items():
        if iri not in m.class_mods or not _checkable(iri):
            continue
        for mod, texts in per.items():
            if mod in m.class_mods[iri]:
                lab = sorted(texts)[0] if texts else ""
                by_mod[mod][lab.lower()].add(iri)
    for mod, groups in sorted(by_mod.items()):
        for lab, iris in sorted(groups.items()):
            if lab and len(iris) > 1:
                m.findings.append(
                    Finding(
                        "DUPLICATE_LABEL",
                        f"label '{lab}' names {len(iris)} classes in {mod}",
                        mod,
                        _pack_of(m, mod),
                        "",
                        0,
                        sorted(iris)[0],
                        {"classes": sorted(iris)},
                    )
                )


def check_virtual(m: Model) -> None:
    for pack, srcs in sorted(m.ingest.items()):
        for src in srcs:
            rt = src.get("record_type") or ""
            cls = m.find_class(rt)
            if not cls:
                m.findings.append(
                    Finding(
                        "INGEST_TYPE_MISSING",
                        f"ingest source {src.get('source_id')} record type {rt or '(none)'} is not a class",
                        pack,
                        pack,
                        DECLARATION,
                        0,
                        KG_NS + "kg#" + rt,
                        {"source_id": src.get("source_id"), "record_type": rt},
                    )
                )
            has_key = bool(src.get("id_field"))
            linked = False
            if cls:
                chain = {cls} | _useful_ancestors(m, cls)
                linked = any((chain & (m.domains.get(p, set()) | m.ranges.get(p, set()))) for p in m.obj_props)
            if not (has_key and linked):
                m.findings.append(
                    Finding(
                        "NO_JOIN_KEY",
                        f"ingest source {src.get('source_id')} ({rt}) "
                        + (
                            "has no id field"
                            if not has_key
                            else "has no class link, so rows cannot be joined across sources"
                        ),
                        pack,
                        pack,
                        DECLARATION,
                        0,
                        cls or "",
                        {"source_id": src.get("source_id"), "record_type": rt, "id_field": src.get("id_field")},
                    )
                )
    for pack, man in sorted(m.manifests.items()):
        for typ, spec in sorted((man.get("schema_mappings") or {}).items()):
            tgt = (spec or {}).get("ontology_class")
            if not tgt or not m.find_class(str(tgt)):
                m.findings.append(
                    Finding(
                        "MAPPING_TARGET_MISSING",
                        f"schema mapping {typ} maps to {tgt!r}, "
                        + ("no class" if not tgt else "which is not a declared class"),
                        pack,
                        pack,
                        DECLARATION,
                        0,
                        KG_NS + "kg#" + str(tgt) if tgt else "",
                        {"type": typ, "ontology_class": tgt},
                    )
                )


# -- bridging ------------------------------------------------------------------------------


def module_graph(m: Model) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Adjacency with reference edges and shared-IRI edges, and the reference-only adjacency."""
    mods = sorted({s.module for s in m.sources})
    ref: dict[str, set[str]] = {x: set() for x in mods}
    both: dict[str, set[str]] = {x: set() for x in mods}
    declared = {**{k: v for k, v in m.class_mods.items()}}
    for k, v in m.prop_mods.items():
        declared.setdefault(k, set()).update(v)
    # class and property edges only; an individual's type bridges EG modules, never packs
    pack_ref = [(i, mod) for i, _, mod, _ in m.refs] + [(i, x) for i, x in m.type_refs if m.kind.get(x) != "pack"]
    # owl:imports bridges Medulla-internal modules only; a pack import of EG is an antipattern (PACK_IMPORTS_CORE)
    for mod, onto in m.imports:
        if m.kind.get(mod) == "pack":
            continue
        for d in m.ontology_mods.get(onto, ()):
            if d != mod:
                for adj in (ref, both):
                    adj[mod].add(d)
                    adj[d].add(mod)
    for pack, man in m.manifests.items():
        for typ, spec in (man.get("schema_mappings") or {}).items():
            t = (spec or {}).get("ontology_class")
            if t and (c := m.find_class(str(t))):
                pack_ref.append((c, pack))
        for res in man.get("resources") or []:
            for rel in res.get("relations") or []:
                for nm, fn in ((rel.get("target"), m.find_class), (rel.get("name"), m.find_prop)):
                    if nm and (c := fn(nm)):
                        pack_ref.append((c, pack))
    for pack, srcs in m.ingest.items():
        for s in srcs:
            if s.get("record_type") and (c := m.find_class(s["record_type"])):
                pack_ref.append((c, pack))
    for iri, mod in pack_ref:
        for d in declared.get(iri, ()):
            if d != mod:
                ref[mod].add(d)
                ref[d].add(mod)
                both[mod].add(d)
                both[d].add(mod)
    for iri, ds in declared.items():
        if len(ds) > 1 and _checkable(iri):
            ordered = sorted(ds)
            for a in ordered:
                for b in ordered:
                    if a != b:
                        both[a].add(b)
    return both, ref


def components(adj: dict[str, set[str]]) -> list[list[str]]:
    seen: set[str] = set()
    comps = []
    for n in sorted(adj):
        if n in seen:
            continue
        comp, todo = [], [n]
        seen.add(n)
        while todo:
            cur = todo.pop()
            comp.append(cur)
            for o in sorted(adj[cur]):
                if o not in seen:
                    seen.add(o)
                    todo.append(o)
        comps.append(sorted(comp))
    return sorted(comps, key=lambda c: (-len(c), c))


def check_bridging(m: Model) -> dict[str, Any]:
    both, ref = module_graph(m)
    comps = components(both)
    ref_comps = components(ref)
    main = set(comps[0]) if comps else set()
    for comp in comps[1:]:
        for mod in comp:
            kind = m.kind.get(mod)
            m.findings.append(
                Finding(
                    "ISLAND_PACK" if kind == "pack" else "ISLAND_MODULE",
                    f"{mod} is not connected to the main component (component of {len(comp)})",
                    mod,
                    _pack_of(m, mod),
                    "",
                    0,
                    "",
                    {"component": comp},
                )
            )
    return {
        "components": len(comps),
        "components_reference_only": len(ref_comps),
        "main_size": len(main),
        "modules": len(both),
        "islands": [c for c in comps[1:]],
    }


# -- competency questions ------------------------------------------------------------------


def _compatible(m: Model, cls: str, expr: set[str]) -> bool:
    chain = {cls} | m.ancestors(cls)
    if expr & ROOTS:
        return True
    return any(e in chain or cls in ({e} | m.ancestors(e)) for e in expr)


def evaluate_question(m: Model, q: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    hops: list[dict[str, Any]] = []
    for h in q.get("hops", []):
        kind = h.get("kind", "edge")
        miss: list[str] = []
        if kind == "edge":
            a, b = m.find_class(h["from"]), m.find_class(h["to"])
            if not a:
                miss.append(f"class {h['from']}")
            if not b:
                miss.append(f"class {h['to']}")
            names = h["property"] if isinstance(h["property"], list) else [h["property"]]
            props = [p for p in (m.find_prop(n) for n in names) if p]
            props = [p for p in props if p in m.obj_props]
            if not props:
                miss.append(f"object property {'|'.join(names)}")
            elif a and b:
                good = [
                    p
                    for p in props
                    if m.domains.get(p)
                    and m.ranges.get(p)
                    and _compatible(m, a, m.domains[p])
                    and _compatible(m, b, m.ranges[p])
                ]
                if not good:
                    p = props[0]
                    dd = ",".join(sorted(local(x) for x in m.domains.get(p, ()))) or "none"
                    rr = ",".join(sorted(local(x) for x in m.ranges.get(p, ()))) or "none"
                    miss.append(f"edge {h['from']} -{local(p)}-> {h['to']} (property domain {dd}, range {rr})")
            label = f"{h['from']} -{'|'.join(names)}-> {h['to']}"
        elif kind == "has_property":
            a = m.find_class(h["class"])
            names = h["property"] if isinstance(h["property"], list) else [h["property"]]
            if not a:
                miss.append(f"class {h['class']}")
            else:
                chain = {a} | m.ancestors(a)
                ok = False
                for n in names:
                    for p in m.prop_mods:
                        if (
                            local(p) == n
                            and _checkable(p)
                            and (chain & m.domains.get(p, set()) or not m.domains.get(p) and False)
                        ):
                            ok = True
                if not ok:
                    miss.append(f"property {'|'.join(names)} with domain {h['class']}")
            label = f"{h['class']} has {'|'.join(names)}"
        elif kind == "shared_ancestor":
            found, pack_cls = [], {}
            for pack, name in sorted(h["packs"].items()):
                c = m.find_class(name, pack)
                if not c or pack not in m.class_mods[c] | {x for r in m.refs for x in [r[2]] if r[0] == c}:
                    miss.append(f"class {name} in pack {pack}")
                    continue
                pack_cls[pack] = c
                found.append({c} | _useful_ancestors(m, c))
            if len(found) == len(h["packs"]):
                common = set.intersection(*found)
                if not common:
                    miss.append(f"shared ancestor of {', '.join(sorted(local(c) for c in pack_cls.values()))}")
                elif h.get("property"):
                    ok = any(local(p) == h["property"] and (common & m.domains.get(p, set())) for p in m.prop_mods)
                    if not ok:
                        miss.append(
                            f"property {h['property']} with a domain in {{{','.join(sorted(local(c) for c in common))}}}"
                        )
            label = "shared ancestor of " + ", ".join(f"{p}:{n}" for p, n in sorted(h["packs"].items()))
        else:
            miss.append(f"unknown hop kind {kind}")
            label = kind
        hops.append({"hop": label, "ok": not miss, "missing": miss, "spec": h})
        missing.extend(miss)
    return {"id": q["id"], "question": q["question"], "pass": not missing, "hops": hops, "missing": missing}


def check_questions(m: Model, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = [evaluate_question(m, q) for q in questions]
    for r in results:
        for hop in r["hops"]:
            for miss in hop["missing"]:
                m.findings.append(
                    Finding(
                        "CQ_PATH_BROKEN",
                        f"{r['id']}: missing {miss}",
                        "",
                        "",
                        "",
                        0,
                        "",
                        {"question": r["id"], "hop": hop["hop"], "missing": miss},
                    )
                )
    return results


# -- fix plan ------------------------------------------------------------------------------


def _suggest_parent(m: Model, name: str) -> tuple[str, str]:
    """Deterministic parent for a new class: longest trailing-token match with a declared class."""
    toks = _tokens(name)
    for i in range(len(toks)):
        tail = "".join(toks[i:])
        for iri in sorted(m.class_mods):
            if _checkable(iri) and _norm(local(iri)) == tail and local(iri) != name:
                return local(iri), "head-noun" if i else "exact"
    return "Concept", "fallback"


def fix_plan(m: Model, results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Exact triples to add, grouped by owning repo. Shared concepts go to EG, system-specific to the pack."""
    plan: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    def add(owner: str, key: str, why: str, triples: list[str]) -> None:
        owner = "epistemic-graph" if owner == "eg" else owner
        plan[owner].setdefault(key, {"why": [], "triples": triples})["why"].append(why)

    def cls_triples(name: str) -> list[str]:
        parent, how = _suggest_parent(m, name)
        return [f":{name} a owl:Class ; rdfs:subClassOf :{parent} .  # parent by {how}"]

    refcount: dict[str, set[str]] = defaultdict(set)
    for f in m.findings:
        if f.code == "DANGLING_REFERENCE" and f.iri:
            refcount[f.iri].add(f.pack)
    for f in m.findings:
        if f.code == "DANGLING_REFERENCE" and f.detail.get("role") == "class":
            name = local(f.iri)
            owner = "epistemic-graph" if len(refcount[f.iri]) > 1 else f.pack
            add(owner, "class:" + name, f"{f.code} {f.file}:{f.line} ({f.pack})", cls_triples(name))
        elif f.code == "DANGLING_REFERENCE" and f.detail.get("role") == "property":
            name = local(f.iri)
            owner = "epistemic-graph" if len(refcount[f.iri]) > 1 else f.pack
            d, r = f.detail.get("domain"), f.detail.get("range")
            if d and r:
                add(
                    owner,
                    "prop:" + name,
                    f"{f.code} manifest {f.pack}",
                    [f":{name} a owl:ObjectProperty ; rdfs:domain :{d} ; rdfs:range :{r} ."],
                )
            else:
                add(
                    owner,
                    "prop:" + name,
                    f"{f.code} {f.file}:{f.line} ({f.pack})",
                    [
                        f":{name} a owl:ObjectProperty ; rdfs:domain :TODO ; rdfs:range :TODO .  # needs reviewer-chosen domain/range"
                    ],
                )
        elif f.code == "INGEST_TYPE_MISSING":
            name = f.detail["record_type"]
            if name:
                add(f.pack, "class:" + name, f"{f.code} {f.detail.get('source_id')}", cls_triples(name))
        elif f.code == "MAPPING_TARGET_MISSING":
            tgt = f.detail.get("ontology_class")
            if tgt:
                add(f.pack, "class:" + str(tgt), f"{f.code} {f.detail['type']}", cls_triples(str(tgt)))
        elif f.code == "UNBRIDGED_SAME_CONCEPT":
            classes = f.detail["classes"]
            key = f.detail["key"]
            shared = next((local(c) for c in classes), key)
            owner_triples = [f":{shared} a owl:Class ; rdfs:subClassOf :{_suggest_parent(m, shared)[0]} ."]
            add("epistemic-graph", "class:" + shared, f"{f.code} {key}", owner_triples)
            for c in classes:
                for pk in sorted(_packs_of(m, c)):
                    if pk != "eg" and local(c) != shared:
                        add(pk, "sub:" + local(c), f"{f.code} {key}", [f":{local(c)} rdfs:subClassOf :{shared} ."])
                    elif pk != "eg":
                        add(
                            pk,
                            "sub:" + local(c) + "@" + shared,
                            f"{f.code} {key}",
                            [
                                f"# {pk} already uses :{shared}; declare it once in EG and remove the local redeclaration"
                            ],
                        )
    for r in results:
        for hop in r["hops"]:
            for miss in hop["missing"]:
                for owner, key, triples in _cq_fix(m, hop["spec"], miss):
                    add(owner, key, f"{r['id']}: {miss}", triples)
    return {o: [{"key": k, **v} for k, v in sorted(items.items())] for o, items in sorted(plan.items())}


def _cq_fix(m: Model, h: dict[str, Any], miss: str) -> list[tuple[str, str, list[str]]]:
    out: list[tuple[str, str, list[str]]] = []
    owner = h.get("owner", "epistemic-graph")
    kind = h.get("kind", "edge")
    if kind == "edge":
        names = h["property"] if isinstance(h["property"], list) else [h["property"]]
        if miss.startswith("class "):
            nm = miss.split()[1]
            out.append((owner, "class:" + nm, [f":{nm} a owl:Class ; rdfs:subClassOf :{_suggest_parent(m, nm)[0]} ."]))
        elif miss.startswith("object property") or miss.startswith("edge"):
            p = names[0]
            out.append(
                (
                    owner,
                    "prop:" + p,
                    [f":{p} a owl:ObjectProperty ; rdfs:domain :{h['from']} ; rdfs:range :{h['to']} ."],
                )
            )
    elif kind == "has_property":
        if miss.startswith("class "):
            nm = miss.split()[1]
            out.append((owner, "class:" + nm, [f":{nm} a owl:Class ; rdfs:subClassOf :{_suggest_parent(m, nm)[0]} ."]))
        else:
            p = (h["property"] if isinstance(h["property"], list) else [h["property"]])[0]
            rng = h.get("range")
            decl = (
                f":{p} a owl:ObjectProperty ; rdfs:domain :{h['class']} ; rdfs:range :{rng} ."
                if rng
                else f":{p} a owl:DatatypeProperty ; rdfs:domain :{h['class']} ; rdfs:range xsd:string ."
            )
            out.append((owner, "prop:" + p, [decl]))
    elif kind == "shared_ancestor":
        shared = h.get("shared", "Issue")
        out.append(
            (
                "epistemic-graph",
                "class:" + shared,
                [f":{shared} a owl:Class ; rdfs:subClassOf :{_suggest_parent(m, shared)[0]} ."],
            )
        )
        for pack, name in sorted(h["packs"].items()):
            out.append((pack, "sub:" + name, [f":{name} a owl:Class ; rdfs:subClassOf :{shared} ."]))
        if h.get("property"):
            out.append(
                (
                    "epistemic-graph",
                    "prop:" + h["property"],
                    [f":{h['property']} a owl:DatatypeProperty ; rdfs:domain :{shared} ; rdfs:range xsd:string ."],
                )
            )
    return out


# -- run + render --------------------------------------------------------------------------


def run(sources: list[Source], questions: list[dict[str, Any]], *, with_plan: bool = True) -> dict[str, Any]:
    m = compose(sources)
    check_orphans(m)
    check_pack_imports(m)
    check_rollup(m)
    check_dangling(m)
    check_properties(m)
    data_only = check_isolated(m)
    check_same_concept(m)
    check_conflicts(m)
    check_virtual(m)
    bridge = check_bridging(m)
    results = check_questions(m, questions)
    findings = sorted(
        (f.as_dict() for f in m.findings),
        key=lambda d: (
            d["code"],
            d["pack"],
            d["module"],
            d.get("file", ""),
            d.get("line", 0),
            d.get("iri", ""),
            d["message"],
        ),
    )
    by_code = Counter(f["code"] for f in findings)
    by_pack: dict[str, Counter] = defaultdict(Counter)
    by_module: dict[str, Counter] = defaultdict(Counter)
    for f in findings:
        if f["pack"]:
            by_pack[f["pack"]][f["code"]] += 1
        if f["module"]:
            by_module[f["module"]][f["code"]] += 1
    result = {
        "summary": {
            "total": len(findings),
            "by_code": {c: by_code.get(c, 0) for c in CODES},
            "by_pack": {k: dict(sorted(v.items())) for k, v in sorted(by_pack.items())},
            "by_module": {k: dict(sorted(v.items())) for k, v in sorted(by_module.items())},
            "modules": len({s.module for s in sources}),
            "classes": sum(1 for i in m.class_mods if _checkable(i)),
            "object_properties": sum(1 for i in m.obj_props if _checkable(i)),
            "triples": len(m.composed),
            "bridging": bridge,
            "questions_passed": sum(1 for r in results if r["pass"]),
            "questions_total": len(results),
        },
        "questions": results,
        "data_only_classes": sorted(local(i) + "@" + "/".join(sorted(m.class_mods[i])) for i in data_only),
        "findings": findings,
    }
    if with_plan:
        result["fix_plan"] = fix_plan(m, results)
    return result


def render_markdown(result: dict[str, Any], title: str = "Ontology graph check") -> str:
    s = result["summary"]
    b = s["bridging"]
    lines = [f"# {title}", ""]
    lines += [
        f"Modules {s['modules']}; classes {s['classes']}; object properties {s['object_properties']}; triples {s['triples']}.",
        f"Connected components: **{b['components']}** (reference edges only: {b['components_reference_only']}); main component holds {b['main_size']} of {b['modules']} modules.",
        f"Competency questions passing: **{s['questions_passed']} of {s['questions_total']}**.",
        "",
        "## Findings per code",
        "",
        "| Code | Count |",
        "|------|------:|",
    ]
    lines += [f"| {c} | {n} |" for c, n in s["by_code"].items()]
    lines += [
        f"| **total** | **{s['total']}** |",
        "",
        "## Worst packs",
        "",
        "| Pack | Findings | Top codes |",
        "|------|---:|-----------|",
    ]
    worst = sorted(s["by_pack"].items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:10]
    for pk, cnt in worst:
        top = ", ".join(f"{c} {n}" for c, n in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:3])
        lines.append(f"| {pk} | {sum(cnt.values())} | {top} |")
    lines += ["", "## Worst EG modules", "", "| Module | Findings | Top codes |", "|--------|---:|-----------|"]
    egm = sorted(
        ((k, v) for k, v in s["by_module"].items() if k.startswith("eg:")), key=lambda kv: (-sum(kv[1].values()), kv[0])
    )[:10]
    for pk, cnt in egm:
        top = ", ".join(f"{c} {n}" for c, n in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:3])
        lines.append(f"| {pk} | {sum(cnt.values())} | {top} |")
    lines += ["", "## Islands", ""]
    for comp in b["islands"]:
        lines.append(f"- {', '.join(comp)}")
    if not b["islands"]:
        lines.append("None.")
    lines += ["", "## Competency questions", ""]
    for r in result["questions"]:
        lines.append(f"- **{r['id']}** {'PASS' if r['pass'] else 'FAIL'}: {r['question']}")
        for hop in r["hops"]:
            mark = "ok" if hop["ok"] else "MISSING " + "; ".join(hop["missing"])
            lines.append(f"  - {hop['hop']}: {mark}")
    lines += ["", f"Data-only classes (allowed, listed): {len(result['data_only_classes'])}."]
    plan = result.get("fix_plan")
    if plan:
        lines += [
            "",
            "## Fix plan by owning repo",
            "",
            "Prefixes: `@prefix : <http://knuckles.team/kg#> .` plus owl, rdfs, xsd. `fallback` parents need a reviewer.",
        ]
        for owner, items in plan.items():
            lines += ["", f"### {owner} ({len(items)} items)", ""]
            for it in items:
                lines.append(
                    f"- `{it['triples'][0]}`  <- {it['why'][0]}"
                    + (f" (+{len(it['why']) - 1} more)" if len(it["why"]) > 1 else "")
                )
    return "\n".join(lines) + "\n"


def exit_code(result: dict[str, Any], warn: bool) -> int:
    return 0 if warn or result["summary"]["total"] == 0 else 1
