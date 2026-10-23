"""connector-ontology-map: propose and apply parent classes for orphan connector classes.

A connector ontology joins the epistemic-graph parent ontology when every class
it declares has a ``rdfs:subClassOf`` path to a parent class. This tool finds
the orphan classes the ``connector-surface-audit`` reports and proposes a parent
for each from deterministic signals, then writes the accepted links.

``propose`` reads each connector's ontology at a git ref (no checkout) and the
parent ontology directory. For each orphan root class (an orphan whose
superclasses, if any, are not orphan classes of the same file) it scores
candidate parent classes from:

* ``exact``: the class local name, label or alias equals a parent class local
  name, label or alias (confidence 1.0, the only signal accepted unreviewed);
* ``head``: the trailing tokens of the local name or label equal a parent class
  name (``GitLabIssue`` ends in ``Issue``);
* ``synonym``: a small curated phrase table; entries naming a class the parent
  ontology lacks are ignored, so a parent class is never invented;
* ``domain``: a property of the connector that shares its name with a parent
  property whose ``rdfs:domain`` or ``rdfs:range`` is a parent class, and whose
  own domain or range is the orphan class;
* ``comment``: the class comment names a parent class as ``:Name`` or ``kg:Name``.

Every proposal carries a confidence and the reasons. A class with no candidate
is listed as a candidate for a new parent class. The result is deterministic:
sorted keys, no timestamps.

``apply`` reads a decisions file ``{"<ClassIRI>": "<ParentIRI>"}`` and writes the
``rdfs:subClassOf`` triple into the connector's ``.ttl`` text, plus
``owl:imports <http://knuckles.team/kg>`` where the header lacks it. Formatting
and comments elsewhere in the file are untouched.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PARENT_IRI = "http://knuckles.team/kg"
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
_OWL = "http://www.w3.org/2002/07/owl#"
_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
_SKOS = "http://www.w3.org/2004/02/skos/core#"
_CLASS_TYPES = {_OWL + "Class", _RDFS + "Class"}
_PROPERTY_TYPES = {_OWL + "ObjectProperty", _OWL + "DatatypeProperty", _OWL + "AnnotationProperty"}
_SUBCLASS = _RDFS + "subClassOf"
_LABELS = (_RDFS + "label", _SKOS + "prefLabel", _SKOS + "altLabel")
# Parent classes too broad to carry meaning as a head-noun match.
GENERIC = {"resource", "entity", "item", "object", "thing", "record", "node", "element", "type", "instance"}

# Curated phrase -> parent class local names, tried in order. Only names the parent
# ontology declares are used. Keys are normalised (lowercase, singular tokens).
SYNONYMS: dict[str, tuple[str, ...]] = {
    # work and documents
    "issue": ("WorkItem", "Ticket"),
    "ticket": ("Ticket", "WorkItem"),
    "epic": ("WorkItem",),
    "story": ("UserStory", "WorkItem"),
    "bug": ("WorkItem",),
    "work item": ("WorkItem",),
    "task": ("WorkItem",),
    "article": ("Document",),
    "page": ("Document",),
    "note": ("Document",),
    "wiki": ("Document",),
    "comment": ("Document",),
    "report": ("Document",),
    "invoice": ("Document",),
    "file": ("File",),
    "attachment": ("File",),
    "reference": ("ExternalGraphReference",),
    "pull request": ("PullRequest",),
    "merge request": ("MergeRequest", "PullRequest"),
    "commit": ("Commit",),
    "test": ("Test",),
    "release": ("Deployment",),
    # people and organisations
    "person": ("Person",),
    "user": ("IdentityUser", "Person"),
    "member": ("Person",),
    "contact": ("Person",),
    "employee": ("Employee", "Person"),
    "customer": ("Person",),
    "lead": ("Person",),
    "organisation": ("Organization",),
    "organization": ("Organization",),
    "company": ("Company", "Organization"),
    "team": ("Team",),
    "group": ("IdentityGroup",),
    "role": ("IdentityRole",),
    "bot": ("Agent",),
    "vendor": ("Vendor",),
    "supplier": ("Supplier",),
    # infrastructure
    "host": ("Host", "Server"),
    "server": ("Server", "Host"),
    "node": ("Server", "Host"),
    "device": ("Device",),
    "fan": ("Device",),
    "controller": ("Device",),
    "sensor": ("Device",),
    "container": ("Container",),
    "image": ("ContainerImage",),
    "registry": ("ContainerRegistry",),
    "stack": ("ContainerStack",),
    "workload": ("Workload",),
    "daemon set": ("Workload",),
    "stateful set": ("Workload",),
    "replica set": ("Workload",),
    "deployment": ("Deployment",),
    "service": ("Service",),
    "ingress": ("ProxyRoute", "Route"),
    "route": ("Route",),
    "tunnel": ("Tunnel",),
    "anomaly": ("HealthAnomaly",),
    "baseline": ("HealthBaseline",),
    "trend": ("HealthTrend",),
    "reading": ("Observation",),
    "sample": ("Observation",),
    "observation": ("Observation",),
    "dns zone": ("DnsZone",),
    "dns record": ("DnsRecord",),
    # security
    "secret": ("Credential",),
    "credential": ("Credential",),
    "key": ("Credential",),
    "token": ("Credential",),
    "policy": ("Policy",),
    "rule": ("GovernanceRule",),
    "control": ("SecurityControl",),
    "security audit": ("SecurityAuditEvent",),
    "consent receipt": ("ConsentRecord",),
    "assessment": ("Assessment",),
    "risk": ("TechnologyRisk",),
    "license": ("License",),
    # events, runs and operations
    "event": ("Event",),
    "alert": ("Event",),
    "incident": ("Incident", "Event"),
    "change": ("Change", "Event"),
    "operation": ("ActionInvocation",),
    "command execution": ("ActionInvocation",),
    "execution": ("ActionInvocation",),
    "step": ("WorkflowStep", "TaskStep"),
    "workflow": ("Workflow",),
    "pipeline": ("PipelineRun", "Pipeline"),
    "schedule": ("Schedule",),
    "trace": ("RunTrace",),
    "run": ("RunEvent",),
    "job": ("AnalyticsJob",),
    # data and models
    "dataset": ("Dataset",),
    "corpus": ("Dataset",),
    "table": ("Dataset",),
    "model": ("Model",),
    "adapter": ("Model",),
    "prompt": ("Prompt",),
    "segment": ("Fragment", "Chunk"),
    "fact sheet": ("EAFactSheet",),
    "account": ("Account",),
    "strategy": ("TradingStrategy",),
    "signal": ("TradingSignal",),
    "backtest": ("BacktestResult",),
    "data source": ("SourceConnection",),
    "tag": ("Tag",),
    "session": ("Session",),
    # media and places
    "movie": ("CreativeWork",),
    "book": ("CreativeWork",),
    "album": ("CreativeWork",),
    "series": ("CreativeWork",),
    "podcast": ("CreativeWork",),
    "game": ("CreativeWork",),
    "recipe": ("CreativeWork",),
    "cookbook": ("CreativeWork",),
    "artist": ("Person",),
    "ingredient": ("Food",),
    "area": ("Place",),
    "package": ("SoftwareComponent",),
    "firmware": ("SoftwareComponent",),
}


# -- a Turtle reader that keeps literals --------------------------------------

_STRING = re.compile(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')
_COMMENT = re.compile(r"(?m)#[^\n]*$")
_IRI = re.compile(r"<([^<>\s]*)>")
_PREFIX = re.compile(r"(?im)^\s*@?prefix\s+([A-Za-z][\w.-]*)?:\s+\x00(\d+)\s*\.?")
_TERMINATOR = re.compile(r"\s\.(?=\s|$)|(?<=[\]>)\w\"'])\.(?=\s|$)")


@dataclass
class Graph:
    triples: list[tuple[str, str, str]] = field(default_factory=list)
    prefixes: dict[str, str] = field(default_factory=dict)

    def objects(self, subject: str | None, predicate: str) -> set[str]:
        return {o for s, p, o in self.triples if p == predicate and (subject is None or s == subject)}

    def subjects(self, predicate: str, objects: set[str]) -> set[str]:
        return {s for s, p, o in self.triples if p == predicate and o in objects}

    def values(self, subject: str, predicates: tuple[str, ...]) -> list[str]:
        """Literal values (without quotes) of ``subject`` under ``predicates``."""
        return sorted({o[1:] for s, p, o in self.triples if s == subject and p in predicates and o.startswith('"')})


def parse(text: str) -> Graph:
    """Parse ``text``; IRIs and prefixed names are expanded, literals kept as ``"value``."""
    iris: list[str] = []
    lits: list[str] = []

    def keep_iri(match: re.Match[str]) -> str:
        iris.append(match.group(1))
        return f" \x00{len(iris)} "

    def keep_lit(match: re.Match[str]) -> str:
        raw = match.group(0)
        quote = raw[:3] if raw[:3] in ('"""', "'''") else raw[0]
        lits.append(raw[len(quote) : -len(quote)])
        return f" \x01{len(lits)} "

    body = _STRING.sub(keep_lit, text)
    body = _IRI.sub(keep_iri, body)
    body = _COMMENT.sub("", body)
    prefixes = {(m.group(1) or ""): iris[int(m.group(2)) - 1] for m in _PREFIX.finditer(body)}
    body = _PREFIX.sub("", body)
    body = re.sub(r"\[[^\[\]]*\]", " _:b ", body)
    graph = Graph(prefixes=prefixes)

    def expand(token: str) -> str:
        if token.startswith("\x00"):
            return iris[int(token[1:]) - 1]
        if token.startswith("\x01"):
            return '"' + lits[int(token[1:]) - 1]
        if token == "a":
            return _RDF_TYPE
        prefix, sep, local = token.partition(":")
        return prefixes[prefix] + local if sep and prefix in prefixes else token

    for statement in _TERMINATOR.split(body):
        tokens = [t for t in statement.replace(";", " ; ").replace(",", " , ").split() if not t.startswith(("@", "^^"))]
        if len(tokens) < 3:
            continue
        subject = expand(tokens[0])
        predicate: str | None = None
        expect_predicate = True
        for token in tokens[1:]:
            if token == ";":
                expect_predicate = True
            elif token == ",":
                continue
            elif expect_predicate:
                predicate, expect_predicate = expand(token), False
            elif predicate is not None:
                graph.triples.append((subject, predicate, expand(token)))
    return graph


# -- names ----------------------------------------------------------------------


def local_name(iri: str) -> str:
    return re.split(r"[#/]", iri.rstrip("#/"))[-1]


def tokens(name: str) -> list[str]:
    """Lowercase singular word tokens of a camelCase, snake_case or spaced name."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    words = [w.lower() for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]
    return [
        w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")) and w != "series" else w
        for w in words
    ]


def key(name: str) -> str:
    return " ".join(tokens(name))


# -- the parent ontology ------------------------------------------------------------


@dataclass
class Parent:
    classes: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_key: dict[str, list[str]] = field(default_factory=dict)
    by_local: dict[str, list[str]] = field(default_factory=dict)
    properties: dict[str, list[str]] = field(default_factory=dict)

    def pick(self, iris: list[str]) -> tuple[str, bool]:
        """The preferred IRI among same-named parent classes, and whether the name is ambiguous."""
        ranked = sorted(iris, key=lambda i: (not i.startswith(PARENT_IRI + "#"), i))
        return ranked[0], len(iris) > 1


def load_parent(directory: Path) -> Parent:
    parent = Parent()
    for path in sorted(directory.glob("*.ttl")):
        g = parse(path.read_text(encoding="utf-8", errors="replace"))
        for iri in sorted(g.subjects(_RDF_TYPE, _CLASS_TYPES)):
            if not iri.startswith("http"):
                continue
            names = {local_name(iri), *g.values(iri, _LABELS)}
            entry = parent.classes.setdefault(iri, {"names": set(), "supers": set()})
            entry["names"] |= names
            entry["supers"] |= g.objects(iri, _SUBCLASS)
        for iri in sorted(g.subjects(_RDF_TYPE, _PROPERTY_TYPES)):
            ends = sorted(g.objects(iri, _RDFS + "domain") | g.objects(iri, _RDFS + "range"))
            if ends:
                parent.properties.setdefault(key(local_name(iri)), [])
                parent.properties[key(local_name(iri))] += ends
    for iri, entry in parent.classes.items():
        for name in entry["names"]:
            if key(name):
                parent.by_key.setdefault(key(name), [])
                if iri not in parent.by_key[key(name)]:
                    parent.by_key[key(name)].append(iri)
        parent.by_local.setdefault(local_name(iri), []).append(iri)
    return parent


# -- one connector ontology file ------------------------------------------------


def orphan_roots(graph: Graph, parent: Parent) -> tuple[list[str], list[str]]:
    """``(orphans, roots)`` of one file, with the audit's reading of ``orphan``."""
    declared = graph.subjects(_RDF_TYPE, _CLASS_TYPES)
    supers = {c: graph.objects(c, _SUBCLASS) for c in declared}
    known = set(parent.classes)
    linked: set[str] = set()
    changed = True
    while changed:
        changed = False
        for cls, ups in supers.items():
            if cls not in linked and cls not in known and ups & (known | linked):
                linked.add(cls)
                changed = True
    orphans = sorted(declared - known - linked)
    roots = [c for c in orphans if not (supers[c] & set(orphans))]
    return orphans, roots


def _candidates(cls: str, graph: Graph, parent: Parent) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def add(iri: str, score: float, reason: str, ambiguous: bool = False) -> None:
        if iri == cls:
            return
        entry = out.setdefault(iri, {"parent": iri, "score": 0.0, "reasons": []})
        entry["reasons"].append(reason)
        entry["score"] = max(entry["score"], score - (0.05 if ambiguous else 0.0))

    own = [local_name(cls), *graph.values(cls, _LABELS)]
    # exact: name, label or alias equals a parent name
    for name in own:
        hit = parent.by_key.get(key(name))
        if hit:
            iri, ambiguous = parent.pick(hit)
            generic = key(local_name(iri)) in GENERIC or local_name(iri).startswith("BFO_")
            add(iri, 0.9 if generic else 1.0, f"exact: '{name}' equals parent class '{local_name(iri)}'", ambiguous)
    # head noun
    for name in own[:2]:
        toks = tokens(name)
        for size in range(len(toks) - 1, 0, -1):
            hit = parent.by_key.get(" ".join(toks[-size:]))
            if hit:
                iri, ambiguous = parent.pick(hit)
                weak = " ".join(toks[-size:]) in GENERIC
                score = (0.4 if weak else 0.6 + 0.1 * min(size, 2) + 0.05 * (len(toks) == size + 1)) - 0.0
                add(iri, score, f"head: '{name}' ends in '{' '.join(toks[-size:])}'", ambiguous)
                break
    # synonym table (also tried on every token, last token first)
    for name in own[:2]:
        toks = tokens(name)
        phrases = [" ".join(toks[i:]) for i in range(len(toks))]
        for phrase in dict.fromkeys(phrases):
            for rank, target in enumerate(SYNONYMS.get(phrase, ())):
                hit = parent.by_local.get(target)
                if hit:
                    iri, _ = parent.pick(hit)
                    add(iri, 0.7 - 0.05 * rank, f"synonym: '{phrase}' -> {target}")
                    break
    # property domain/range
    for prop in graph.subjects(_RDF_TYPE, _PROPERTY_TYPES):
        if cls in graph.objects(prop, _RDFS + "domain") | graph.objects(prop, _RDFS + "range"):
            ends = sorted({e for e in parent.properties.get(key(local_name(prop)), []) if e in parent.classes})
            if len(ends) == 1:
                add(
                    ends[0],
                    0.5,
                    f"domain: property '{local_name(prop)}' is a parent property over {local_name(ends[0])}",
                )
    # comment reference
    comments = " ".join(graph.values(cls, (_RDFS + "comment", _SKOS + "definition")))
    for ref in dict.fromkeys(re.findall(r"(?<![\w/])(?:kg)?:([A-Z][A-Za-z0-9]+)\b", comments)):
        hit = parent.by_local.get(ref)
        if hit:
            iri, _ = parent.pick(hit)
            add(iri, 0.6, f"comment: names parent class ':{ref}'")
    for entry in out.values():
        agreeing = len({r.split(":")[0] for r in entry["reasons"]})
        if entry["score"] < 1.0:
            entry["score"] = min(0.95, entry["score"] + 0.05 * (agreeing - 1))
        entry["score"] = round(entry["score"], 2)
        entry["reasons"] = sorted(set(entry["reasons"]))
    return out


def propose_file(text: str, parent: Parent) -> dict[str, Any]:
    graph = parse(text)
    orphans, roots = orphan_roots(graph, parent)
    proposals = []
    for cls in roots:
        ranked = sorted(_candidates(cls, graph, parent).values(), key=lambda c: (-c["score"], c["parent"]))
        best = ranked[0] if ranked else None
        proposals.append(
            {
                "class": cls,
                "label": (graph.values(cls, (_RDFS + "label",)) or [local_name(cls)])[0],
                "proposed_parent": best["parent"] if best else None,
                "confidence": best["score"] if best else 0.0,
                "reasons": best["reasons"] if best else ["no deterministic signal"],
                "auto": bool(best and best["score"] >= 1.0),
                "alternatives": [{"parent": c["parent"], "confidence": c["score"]} for c in ranked[1:3]],
                "subclasses_resolved": sorted(c for c in orphans if c != cls and _below(graph, c, cls)),
            }
        )
    imports = graph.objects(None, _OWL + "imports")
    return {
        "orphans": len(orphans),
        "imports_parent": any(i == PARENT_IRI or i.startswith(PARENT_IRI + "/") for i in imports),
        "proposals": proposals,
    }


def _below(graph: Graph, cls: str, ancestor: str) -> bool:
    seen: set[str] = set()
    todo = [cls]
    while todo:
        cur = todo.pop()
        for up in graph.objects(cur, _SUBCLASS):
            if up == ancestor:
                return True
            if up not in seen:
                seen.add(up)
                todo.append(up)
    return False


# -- reading a repository at a ref -----------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return done.stdout if done.returncode == 0 else ""


def ontology_files(repo: Path, ref: str) -> list[str]:
    paths = _git(repo, "ls-tree", "-r", "--name-only", ref).splitlines()
    return sorted(
        p for p in paths if "/ontology/" in p and p.endswith(".ttl") and "/shapes/" not in p and p.count("/") == 2
    )


def propose_repo(repo: Path, ref: str, parent: Parent) -> dict[str, Any]:
    files = {}
    for path in ontology_files(repo, ref):
        result = propose_file(_git(repo, "show", f"{ref}:{path}"), parent)
        if result["orphans"] or not result["imports_parent"]:
            files[path] = result
    return {"repository": repo.name, "ref": _git(repo, "rev-parse", "--short", ref).strip(), "files": files}


# -- apply ---------------------------------------------------------------------------------


def _short(iri: str, prefixes: dict[str, str]) -> str:
    best = max(
        (p for p, ns in prefixes.items() if iri.startswith(ns) and re.fullmatch(r"[\w.-]+", iri[len(ns) :])),
        key=lambda p: len(prefixes[p]),
        default=None,
    )
    return f"{best}:{iri[len(prefixes[best]) :]}" if best is not None else f"<{iri}>"


def apply_links(text: str, links: dict[str, str]) -> tuple[str, list[str]]:
    """Insert ``rdfs:subClassOf`` lines for ``links``; return the new text and the problems."""
    prefixes = parse(text).prefixes
    problems: list[str] = []
    lines = text.split("\n")
    for cls, parent_iri in sorted(links.items()):
        subject = _short(cls, prefixes)
        pattern = re.compile(rf"^{re.escape(subject)}\s+a\s+(owl:Class|rdfs:Class)\b(.*)$")
        for index, line in enumerate(lines):
            m = pattern.match(line)
            if not m:
                continue
            triple = f"rdfs:subClassOf {_short(parent_iri, prefixes)}"
            if m.group(2).rstrip().endswith("."):  # a one-line statement
                lines[index] = line.rstrip()[:-1].rstrip() + f" ;\n    {triple} ."
            elif m.group(2).rstrip().endswith(";"):
                lines[index] = f"{line.rstrip()}\n    {triple} ;"
            elif m.group(2).rstrip().endswith(","):
                problems.append(f"{cls}: type list ends in a comma")
            else:
                problems.append(f"{cls}: unsupported statement shape")
            break
        else:
            problems.append(f"{cls}: no 'a owl:Class' statement found")
    result = "\n".join(lines)
    if not any(
        i == PARENT_IRI or i.startswith(PARENT_IRI + "/") for i in parse(result).objects(None, _OWL + "imports")
    ):
        header = re.search(r"(?m)^(<[^>]+>|\S+)\s+a\s+owl:Ontology\s*([;.])", result)
        if header and header.group(2) == ";":
            result = result[: header.end()] + f"\n    owl:imports <{PARENT_IRI}> ;" + result[header.end() :]
        elif header:
            result = (
                result[: header.end() - 1].rstrip() + f" ;\n    owl:imports <{PARENT_IRI}> ." + result[header.end() :]
            )
        else:
            problems.append("no owl:Ontology header to carry owl:imports")
    return result, problems


def apply_repo(root: Path, decisions: dict[str, dict[str, str]]) -> list[str]:
    """Write ``{file: {class: parent}}`` into the checkout at ``root``; return the problems."""
    problems: list[str] = []
    for rel, links in sorted(decisions.items()):
        path = root / rel
        text = path.read_text(encoding="utf-8")
        new, bad = apply_links(text, links)
        problems += [f"{rel}: {p}" for p in bad]
        path.write_text(new, encoding="utf-8")
    return problems


# -- review: turn proposals plus reviewer overrides into decisions -----------------


ACCEPT_AT = 0.7


def decide(record: dict[str, Any], overrides: dict[str, str | None], parent: Parent) -> dict[str, Any]:
    """Decisions for one repository record.

    ``overrides`` maps a class local name to a parent class local name, or ``None`` to reject.
    An exact proposal is accepted unreviewed; any other is accepted at ``ACCEPT_AT`` or more
    unless overridden. An override names a parent class that must exist in the parent ontology.
    """
    links: dict[str, dict[str, str]] = {}
    candidates: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for path, result in sorted(record["files"].items()):
        for prop in result["proposals"]:
            name = local_name(prop["class"])
            parent_iri, how = prop["proposed_parent"], ""
            if name in overrides:
                target = overrides[name]
                if target is None:
                    parent_iri, how = None, "review: no parent fits"
                else:
                    hit = parent.by_local.get(target)
                    if not hit:
                        raise ValueError(
                            f"{record['repository']}:{name}: parent class {target!r} is not in the parent ontology"
                        )
                    parent_iri, how = parent.pick(hit)[0], "review: chosen"
            elif prop["auto"]:
                how = "auto: exact"
            elif parent_iri and prop["confidence"] >= ACCEPT_AT:
                how = "review: accepted proposal"
            else:
                parent_iri = None
            if parent_iri:
                links.setdefault(path, {})[prop["class"]] = parent_iri
                accepted.append(
                    {"class": prop["class"], "parent": parent_iri, "how": how, "confidence": prop["confidence"]}
                )
            else:
                candidates.append(
                    {
                        "class": prop["class"],
                        "label": prop["label"],
                        "file": path,
                        "rejected_proposal": prop["proposed_parent"],
                        "subclasses_resolved": prop["subclasses_resolved"],
                    }
                )
    return {
        "repository": record["repository"],
        "links": links,
        "accepted": accepted,
        "new_parent_candidates": candidates,
    }


_TEST_TEMPLATE = r'''"""Every class of the packaged ontology reaches an epistemic-graph parent class ({spec_id})."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.spec("{spec_id}")

PARENT_IRI = "http://knuckles.team/kg"
ONTOLOGIES = sorted((Path(__file__).resolve().parents[1] / "{package}" / "ontology").glob("*.ttl"))
OWL = "http://www.w3.org/2002/07/owl#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SUBCLASS = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
# Parent classes of the epistemic-graph ontology that this connector links to or redeclares.
PARENT_CLASSES = frozenset(
    (
{parents}
    )
)
# Classes for which the parent ontology has no fitting class yet. Each is a candidate for a new
# parent class (see the orphan mapping report); a class leaves this set when it gains a parent.
PENDING_NEW_PARENT: frozenset[str] = {pending}

_STRING = re.compile(r'"""(?:.|\n)*?"""|"(?:[^"\\\n]|\\.)*"')
_IRI = re.compile(r"<([^<>\s]*)>")
_PREFIX = re.compile(r"(?im)^\s*@?prefix\s+([A-Za-z][\w.-]*)?:\s+\x00(\d+)\s*\.?")
_END = re.compile(r"\s\.(?=\s|$)|(?<=[\]>)\w\"'])\.(?=\s|$)")


def _triples(text: str) -> list[tuple[str, str, str]]:
    """Subject, predicate and object of a Turtle file; names are expanded, literals dropped."""
    iris: list[str] = []

    def keep(match: re.Match[str]) -> str:
        iris.append(match.group(1))
        return f" \x00{{len(iris)}} "

    body = re.sub(r"(?m)#[^\n]*$", "", _IRI.sub(keep, _STRING.sub(' "" ', text)))
    prefixes = {{m.group(1) or "": iris[int(m.group(2)) - 1] for m in _PREFIX.finditer(body)}}
    body = re.sub(r"\[[^\[\]]*\]", " _:b ", _PREFIX.sub("", body))

    def expand(token: str) -> str:
        if token.startswith("\x00"):
            return iris[int(token[1:]) - 1]
        prefix, sep, local = token.partition(":")
        return prefixes[prefix] + local if sep and prefix in prefixes else RDF_TYPE if token == "a" else token

    triples: list[tuple[str, str, str]] = []
    for statement in _END.split(body):
        tokens = statement.replace(";", " ; ").replace(",", " , ").split()
        subject, predicate, fresh = "", "", True
        for index, token in enumerate(tokens):
            if index == 0:
                subject = expand(token)
            elif token == ";":
                fresh = True
            elif token != ",":
                if fresh:
                    predicate, fresh = expand(token), False
                else:
                    triples.append((subject, predicate, expand(token)))
    return triples


def _orphans(triples: list[tuple[str, str, str]]) -> set[str]:
    declared = {{s for s, p, o in triples if p == RDF_TYPE and o == OWL + "Class"}}
    linked: set[str] = set()
    changed = True
    while changed:
        changed = False
        for cls in declared - linked - PARENT_CLASSES:
            ups = {{o for s, p, o in triples if s == cls and p == SUBCLASS}}
            if ups & (PARENT_CLASSES | linked):
                linked.add(cls)
                changed = True
    return declared - linked - PARENT_CLASSES


@pytest.mark.parametrize("path", ONTOLOGIES, ids=lambda p: p.name)
def test_ontology_joins_the_parent_graph(path: Path) -> None:
    triples = _triples(path.read_text(encoding="utf-8"))
    declared = {{s for s, p, o in triples if p == RDF_TYPE and o == OWL + "Class"}}
    if not declared:
        pytest.skip("declares no classes")
    imports = {{o for s, p, o in triples if p == OWL + "imports"}}
    assert any(i == PARENT_IRI or i.startswith(PARENT_IRI + "/") for i in imports)
    assert _orphans(triples) == PENDING_NEW_PARENT & declared
'''


def scaffold_test(
    root: Path, spec_id: str, links: dict[str, dict[str, str]], pending: dict[str, list[str]], parent: Parent
) -> Path:
    """Write ``tests/test_ontology_parent_link.py`` for the connector checkout at ``root``."""
    files = sorted(root.glob("*/ontology/*.ttl"))
    package = files[0].relative_to(root).parts[0]
    used: set[str] = set()
    pend: set[str] = set()
    for path in files:
        graph = parse(path.read_text(encoding="utf-8"))
        mentioned = {t for triple in graph.triples for t in triple}
        used |= {iri for iri in mentioned if iri in parent.classes}
    for classes in pending.values():
        pend |= set(classes)

    def block(items: set[str]) -> str:
        return "\n".join(f'        "{iri}",' for iri in sorted(items)) or ""

    pending_literal = "frozenset(\n    (\n" + block(pend) + "\n    )\n)" if pend else "frozenset()"
    text = _TEST_TEMPLATE.format(spec_id=spec_id, package=package, parents=block(used), pending=pending_literal)
    out = root / "tests" / "test_ontology_parent_link.py"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-ontology-map", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("propose", help="propose parent classes for the orphan classes of a fleet at a ref")
    p.add_argument("--fleet", type=Path, required=True)
    p.add_argument("--ref", default="origin/main")
    p.add_argument("--parent-ontology", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True, help="directory receiving <repository>.json")
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("repository", nargs="*", help="limit to these repositories")
    d = sub.add_parser("decide", help="turn proposals and reviewer overrides into decisions")
    d.add_argument("--proposals", type=Path, required=True)
    d.add_argument("--overrides", type=Path, required=True, help='JSON {"<repository>": {"<Class>": "<Parent>"|null}}')
    d.add_argument("--parent-ontology", type=Path, required=True)
    d.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("scaffold", help="write the connector's parent-link test from decisions")
    c.add_argument("--root", type=Path, default=Path.cwd())
    c.add_argument("--decided", type=Path, required=True, help="a decision file written by decide")
    c.add_argument("--spec-id", required=True)
    c.add_argument("--parent-ontology", type=Path, required=True)
    a = sub.add_parser("apply", help="write accepted links into a connector checkout")
    a.add_argument("--root", type=Path, default=Path.cwd())
    a.add_argument(
        "--decisions",
        type=Path,
        required=True,
        help='JSON {"<file>": {"<class>": "<parent>"}}, or a decision file from decide',
    )
    g = sub.add_parser("graph-check", help="validate that every ontology is reachable and bridged (PIPE-GATES-R016)")
    g.add_argument("--fleet", type=Path, required=True, help="directory of connector repositories")
    g.add_argument("--eg-repo", type=Path, required=True, help="the epistemic-graph repository")
    g.add_argument("--ref", default="origin/main", help="git ref read in every repository")
    g.add_argument("--eg-extra-ref", default=None, help="a ref whose changed EG ontology files overlay the base")
    g.add_argument("--exclude", action="append", default=[])
    g.add_argument("--questions", type=Path, default=None, help="competency questions JSON (default: packaged)")
    g.add_argument("--json", type=Path, default=None, help="write the full result as JSON")
    g.add_argument("--markdown", type=Path, default=None, help="write the Markdown report")
    g.add_argument("--warn", action="store_true", help="report findings but always exit 0")
    args = parser.parse_args(argv)
    if args.command == "graph-check":
        from pipelines_hooks.hygiene import ontology_graph_check as ogc

        sources = ogc.eg_sources(args.eg_repo, args.ref, args.eg_extra_ref)
        sources += ogc.fleet_sources(args.fleet, args.ref, args.exclude)
        qpath = args.questions or ogc.DEFAULT_CQ
        questions = json.loads(qpath.read_text(encoding="utf-8"))["questions"]
        result = ogc.run(sources, questions)
        if args.json:
            args.json.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        if args.markdown:
            args.markdown.write_text(ogc.render_markdown(result), encoding="utf-8")
        for code, n in result["summary"]["by_code"].items():
            if n:
                print(f"{code}: {n}")
        return ogc.exit_code(result, args.warn)
    if args.command == "apply":
        loaded = json.loads(args.decisions.read_text(encoding="utf-8"))
        problems = apply_repo(args.root, loaded.get("links", loaded) if "new_parent_candidates" in loaded else loaded)
        for line in problems:
            print(line)
        return 1 if problems else 0
    parent = load_parent(args.parent_ontology)
    if args.command == "scaffold":
        decided = json.loads(args.decided.read_text(encoding="utf-8"))
        pending: dict[str, list[str]] = {}
        for entry in decided["new_parent_candidates"]:
            pending.setdefault(entry["file"], []).append(entry["class"])
            pending[entry["file"]] += entry["subclasses_resolved"]
        print(scaffold_test(args.root, args.spec_id, decided["links"], pending, parent))
        return 0
    if args.command == "decide":
        overrides = json.loads(args.overrides.read_text(encoding="utf-8"))
        args.out.mkdir(parents=True, exist_ok=True)
        for path in sorted(args.proposals.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            decided = decide(record, overrides.get(record["repository"], {}), parent)
            (args.out / path.name).write_text(json.dumps(decided, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    repos = sorted(r for r in args.fleet.iterdir() if (r / ".git").exists() and r.name not in set(args.exclude))
    for repo in repos:
        if args.repository and repo.name not in args.repository:
            continue
        record = propose_repo(repo, args.ref, parent)
        if record["files"]:
            (args.out / f"{repo.name}.json").write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    return 0
