"""connector-ontology-map fix: deterministic ontology codemod for connector packs (PIPE-GATES-R016.6 to R016.9).

Rules, each deterministic, idempotent and order-independent (every decision is taken on the *original*
composed graph, never on a half-patched one). Only pack ``.ttl`` files are patched:

* R1 drop pack ``owl:imports`` of EG.        * R2 stop redeclaring EG classes (subClassOf, label, comment).
* R3 exact-name roll-up to an EG class.      * R4 reviewed override table (data, checked in).
* R5 head-noun proposal (review queue only). * R6 null ``schema_mappings`` (report only, no patch).
* R7 rewrite dangling IRIs to a declared one. * R8 infer untyped property domain/range (SHACL, manifest relations).

``ISOLATED_CLASS`` is listed, never fixed. Everything not fixed lands in the review queue.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from pipelines_hooks.hygiene import ontology_graph_check as ogc

SH = ogc.SH
DEFAULT_OVERRIDES = Path(__file__).with_name("ontology_codemod_overrides.json")
RULES = ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8")
RDFS_COMMENT = RDFS.comment


def singular(word: str) -> str:
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "xes", "ches", "shes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        return w[:-1]
    return w


def norm_key(text: str) -> str:
    """Case-, punctuation- and plural-insensitive key shared by R3 and R7."""
    parts = re.split(r"[^A-Za-z0-9]+", text.strip())
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return "".join(parts[:-1]).lower() + singular(parts[-1])


# -- Turtle statement surgery --------------------------------------------------------------


def split_statements(text: str) -> list[str]:
    """Split Turtle text into chunks, each ending at a top-level statement terminator."""
    out: list[str] = []
    i, n, start, depth = 0, len(text), 0, 0
    while i < n:
        c = text[i]
        if c == "#":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "<":
            j = text.find(">", i)
            i = (j if j != -1 else n - 1) + 1
            continue
        if c in "\"'":
            q = c * 3 if text.startswith(c * 3, i) else c
            i += len(q)
            while i < n and not text.startswith(q, i):
                i += 2 if text[i] == "\\" else 1
            i += len(q)
            continue
        if c in "[(":
            depth += 1
        elif c in "])":
            depth -= 1
        elif c == "." and depth == 0 and (i + 1 >= n or text[i + 1] in " \t\r\n#"):
            out.append(text[start : i + 1])
            start = i + 1
        i += 1
    if text[start:].strip():
        out.append(text[start:])
    return out


def _lead(chunk: str) -> tuple[str, str]:
    """Split a chunk into leading blank/comment lines and the statement body."""
    lines = chunk.split("\n")
    k = 0
    while k < len(lines) - 1 and (not lines[k].strip() or lines[k].lstrip().startswith("#")):
        k += 1
    return "\n".join(lines[:k]) + ("\n" if k else ""), "\n".join(lines[k:])


def drop_triples(text: str, drop: Any) -> tuple[str, int]:
    """Remove every triple of a top-level subject for which ``drop(s, p, o)`` is true; count removed triples."""
    chunks = split_statements(text)
    header = "\n".join(c.strip() for c in chunks if re.match(r"\s*(@prefix|@base|PREFIX|BASE)", _lead(c)[1], re.I))
    out, removed = [], 0
    for chunk in chunks:
        lead, body = _lead(chunk)
        if re.match(r"\s*(@prefix|@base|PREFIX|BASE)", body, re.I):
            out.append(chunk)
            continue
        g = Graph(bind_namespaces="none")  # only the file's own prefixes, no rdflib defaults (schema1:)
        try:
            g.parse(data=header + "\n" + body, format="turtle")
        except Exception:  # noqa: BLE001 - leave an unparseable statement alone
            out.append(chunk)
            continue
        kill = [(s, p, o) for s, p, o in g if isinstance(s, URIRef) and drop(str(s), p, o)]
        if not kill:
            out.append(chunk)
            continue
        removed += len(kill)
        for t in kill:
            g.remove(t)
        if not len(g):
            out.append(lead.rstrip("\n") + ("\n" if lead.strip() else ""))
            continue
        ser = g.serialize(format="turtle")
        ser = "\n".join(ln for ln in ser.splitlines() if not ln.startswith("@prefix")).strip("\n")
        out.append(lead + ser + "\n")
    return "".join(out), removed


def _n3(iri: str, g: Graph | None) -> str:
    if g is not None:
        try:
            pfx, ns, loc = g.namespace_manager.compute_qname(iri, generate=False)
            if pfx and re.fullmatch(r"[A-Za-z_][\w-]*", loc):
                return f"{pfx}:{loc}"
        except Exception:  # noqa: BLE001
            pass
    return f"<{iri}>"


def append_triples(text: str, g: Graph | None, rule: str, triples: list[tuple[str, str, str]]) -> str:
    if not triples:
        return text
    body = "".join(f"{_n3(s, g)} {_n3(p, g)} {_n3(o, g)} .\n" for s, p, o in sorted(triples))
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}\n# ontology-codemod {rule}\n{body}"


def rewrite_iri(text: str, g: Graph | None, old: str, new: str) -> str:
    """Replace one IRI wherever it is written (angle form or prefixed form)."""
    text = text.replace(f"<{old}>", f"<{new}>")
    if g is not None:
        for pfx, ns_ref in g.namespaces():
            ns = str(ns_ref)
            if old.startswith(ns) and re.fullmatch(r"[\w-]+", old[len(ns) :]):
                tgt = (
                    f"{pfx}:{new[len(ns) :]}"
                    if new.startswith(ns) and re.fullmatch(r"[\w-]+", new[len(ns) :])
                    else f"<{new}>"
                )
                text = re.sub(rf"(?<![\w:.\-<]){re.escape(pfx)}:{re.escape(old[len(ns) :])}(?![\w\-])", tgt, text)
    return text


# -- planning ------------------------------------------------------------------------------


class Plan:
    """Decisions on the original composed model, grouped per source file."""

    def __init__(self, m: ogc.Model, overrides: dict[str, Any]) -> None:
        self.m = m
        self.overrides = overrides
        self.drop_imports: dict[tuple[str, str], set[str]] = defaultdict(set)  # (mod, path) -> ontology IRIs
        self.drop_redecl: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.add: dict[tuple[str, str], dict[str, list[tuple[str, str, str]]]] = defaultdict(lambda: defaultdict(list))
        self.rewrite: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
        self.counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.queue: list[dict[str, Any]] = []
        self.listed: dict[str, list[str]] = defaultdict(list)
        self.eg_by_key: dict[str, set[str]] = defaultdict(set)
        self.eg_props_by_key: dict[str, set[str]] = defaultdict(set)
        self.pack_by_key: dict[str, set[str]] = defaultdict(set)
        self.pack_props_by_key: dict[str, set[str]] = defaultdict(set)
        self.eg_classes = sorted(i for i in m.class_mods if ogc._checkable(i) and ogc._eg_declared(m, i))
        for i in self.eg_classes:
            for k in {norm_key(ogc.local(i)), *(norm_key(x) for per in m.labels.get(i, {}).values() for x in per)}:
                if k:
                    self.eg_by_key[k].add(i)
        for i in m.class_mods:
            if ogc._checkable(i):
                self.pack_by_key[norm_key(ogc.local(i))].add(i)
        for i in m.prop_mods:
            if ogc._checkable(i):
                self.pack_props_by_key[norm_key(ogc.local(i))].add(i)

    def hit(self, repo: str, rule: str) -> None:
        self.counts[repo][rule] += 1

    def review(self, repo: str, rule: str, subject: str, candidates: list[str], reason: str, file: str = "") -> None:
        self.queue.append(
            {
                "repo": repo,
                "rule": rule,
                "subject": subject,
                "candidates": sorted(candidates),
                "reason": reason,
                "file": file,
            }
        )

    def decl_file(self, repo: str, iri: str) -> tuple[str, str] | None:
        for s in sorted(self.m.sources, key=lambda x: x.path):
            if (
                s.module == repo
                and s.graph is not None
                and s.path.endswith(".ttl")
                and (URIRef(iri), RDF.type, None) in s.graph
            ):
                return (repo, s.path)
        return None

    def run(self) -> None:
        m = self.m
        packs = sorted({s.module for s in m.sources if s.kind == "pack"})
        for repo in packs:
            self.r1(repo)
            self.r2(repo)
            self.r345(repo)
            self.r6(repo)
            self.r7(repo)
            self.r8(repo)
            self.listing(repo)

    def r1(self, repo: str) -> None:
        for mod, path, onto in sorted(set(self.m.import_refs)):
            if mod == repo and self.m.kind.get(mod) == "pack" and ogc._is_eg_import(self.m, onto):
                self.drop_imports[(mod, path)].add(onto)
                self.hit(repo, "R1")

    def r2(self, repo: str) -> None:
        m = self.m
        for iri in sorted(m.class_mods):
            if not ogc._checkable(iri) or repo not in m.class_mods[iri] or not ogc._eg_declared(m, iri):
                continue
            for s in m.sources:
                if s.module == repo and s.graph is not None and s.path.endswith(".ttl"):
                    n = sum(
                        1 for p in (RDFS.subClassOf, RDFS.label, RDFS_COMMENT) for _ in s.graph.objects(URIRef(iri), p)
                    )
                    if n:
                        self.drop_redecl[(repo, s.path)].add(iri)
                        self.counts[repo]["R2"] += n

    def _eg_candidates(self, repo: str, iri: str) -> set[str]:
        keys = {norm_key(ogc.local(iri))}
        keys |= {norm_key(x) for x in self.m.labels.get(iri, {}).get(repo, set())}
        out: set[str] = set()
        for k in keys:
            if k:
                out |= self.eg_by_key.get(k, set())
        out.discard(iri)
        return out

    def r345(self, repo: str) -> None:
        m = self.m
        table = {**self.overrides.get("*", {}), **self.overrides.get(repo, {})}
        for iri in sorted(m.class_mods):
            if not ogc._checkable(iri) or repo not in m.class_mods[iri] or ogc._eg_declared(m, iri):
                continue
            if any(ogc._eg_declared(m, a) for a in m.ancestors(iri)):
                continue
            name = ogc.local(iri)
            loc = self.decl_file(repo, iri)
            if name in table:
                tgt = table[name]
                cand = sorted(i for i in self.eg_classes if ogc.local(i) == tgt) if tgt else []
                if tgt and len(cand) == 1 and loc:
                    self.add[loc]["R4"].append((iri, str(RDFS.subClassOf), cand[0]))
                    self.hit(repo, "R4")
                else:
                    why = "audited as pack-local (null)" if not tgt else f"override target {tgt} is not an EG class"
                    self.review(repo, "R4", name, cand, why, loc[1] if loc else "")
                continue
            cands = self._eg_candidates(repo, iri)
            if len(cands) == 1 and loc:
                self.add[loc]["R3"].append((iri, str(RDFS.subClassOf), next(iter(cands))))
                self.hit(repo, "R3")
                continue
            if len(cands) > 1:
                self.review(repo, "R3", name, sorted(cands), "ambiguous exact-name match", loc[1] if loc else "")
                continue
            toks = ogc._tokens(name)
            head = self.eg_by_key.get(norm_key(toks[-1])) if len(toks) > 1 else None
            head = {h for h in (head or set()) if h != iri}
            if head:
                self.review(
                    repo, "R5", name, sorted(head), f"head noun '{toks[-1]}' matches an EG class", loc[1] if loc else ""
                )
            else:
                self.review(repo, "R5", name, [], "no exact-name, override or head-noun match", loc[1] if loc else "")

    def r6(self, repo: str) -> None:
        man = self.m.manifests.get(repo) or {}
        for typ, spec in sorted((man.get("schema_mappings") or {}).items()):
            if (spec or {}).get("ontology_class") is None:
                tgt = self.m.find_class(str(typ))
                self.review(
                    repo,
                    "R6",
                    str(typ),
                    [ogc.local(tgt)] if tgt else [],
                    "resolves to a class in the composed graph (report only, manifests are not patched)"
                    if tgt
                    else "no class of that name; never invented",
                    ogc.DECLARATION,
                )

    def r7(self, repo: str) -> None:
        m = self.m
        seen: set[tuple[str, str]] = set()
        for iri, role, mod, path in sorted(set(m.refs)):
            if mod != repo or not ogc._checkable(iri) or (iri, path) in seen:
                continue
            ok = m.declared_class(iri) if role == "class" else m.declared_prop(iri)
            if ok or (role == "class" and m.declared_prop(iri)):
                continue
            seen.add((iri, path))
            key = norm_key(ogc.local(iri))
            pool = self.pack_by_key if role == "class" else self.pack_props_by_key
            cands = {c for c in pool.get(key, set()) if c != iri}
            if len(cands) == 1:
                self.rewrite[(repo, path)][iri] = next(iter(cands))
                self.hit(repo, "R7")
            else:
                self.review(
                    repo, "R7", ogc.local(iri), [ogc.local(c) for c in cands], f"dangling {role} reference", path
                )

    def r8(self, repo: str) -> None:
        m = self.m
        dom: dict[str, set[str]] = defaultdict(set)
        rng: dict[str, set[str]] = defaultdict(set)
        for s in m.sources:
            if s.module != repo or s.graph is None or not s.path.endswith(".ttl"):
                continue
            g = s.graph
            for shape in g.subjects(URIRef(SH + "targetClass"), None):
                for tc in g.objects(shape, URIRef(SH + "targetClass")):
                    for prop in g.objects(shape, URIRef(SH + "property")):
                        for path_node in g.objects(prop, URIRef(SH + "path")):
                            if isinstance(path_node, URIRef) and isinstance(tc, URIRef):
                                p = str(path_node)
                                dom[p].add(str(tc))
                                for c in g.objects(prop, URIRef(SH + "class")):
                                    if isinstance(c, URIRef):
                                        rng[p].add(str(c))
        for res in (m.manifests.get(repo) or {}).get("resources") or []:
            for rel in res.get("relations") or []:
                rp = m.find_prop(rel.get("name") or "")
                a, b = m.find_class(res.get("name") or ""), m.find_class(rel.get("target") or "")
                if rp and a:
                    dom[rp].add(a)
                if rp and b:
                    rng[rp].add(b)
        for p in sorted(m.obj_props):
            if not ogc._checkable(p) or repo not in m.prop_mods.get(p, ()):
                continue
            loc = None
            for s in sorted(m.sources, key=lambda x: x.path):
                if (
                    s.module == repo
                    and s.graph is not None
                    and s.path.endswith(".ttl")
                    and (URIRef(p), RDF.type, None) in s.graph
                ):
                    loc = (repo, s.path)
                    break
            for side, have, inferred, pred in (
                ("domain", m.domains, dom, RDFS.domain),
                ("range", m.ranges, rng, RDFS.range),
            ):
                if have.get(p):
                    continue
                cands = sorted(inferred.get(p, set()))
                if len(cands) == 1 and loc:
                    self.add[loc]["R8"].append((p, str(pred), cands[0]))
                    self.hit(repo, "R8")
                else:
                    self.review(
                        repo,
                        "R8",
                        ogc.local(p),
                        [ogc.local(c) for c in cands],
                        f"untyped {side}",
                        loc[1] if loc else "",
                    )

    def listing(self, repo: str) -> None:
        pass


# -- applying ------------------------------------------------------------------------------


def patch_sources(sources: list[ogc.Source], overrides: dict[str, Any]) -> tuple[list[ogc.Source], Plan]:
    """Return patched copies of the sources and the plan (original sources are not modified)."""
    m = ogc.compose(sources)
    plan = Plan(m, overrides)
    plan.run()
    # isolated classes: listed only
    probe = Model_findings(m)
    for f in probe:
        if f.code == "ISOLATED_CLASS" and f.pack:
            plan.listed[f.pack].append(ogc.local(f.iri))
    out: list[ogc.Source] = []
    for s in sources:
        key = (s.module, s.path)
        text = s.text
        if s.kind == "pack" and s.graph is not None and s.path.endswith(".ttl"):
            imports = plan.drop_imports.get(key, set())
            redecl = plan.drop_redecl.get(key, set())
            if imports or redecl:
                text, _ = drop_triples(
                    text,
                    lambda subj, p, o, imports=imports, redecl=redecl: (
                        (p == OWL.imports and str(o) in imports)
                        or (subj in redecl and p in (RDFS.subClassOf, RDFS.label, RDFS_COMMENT))
                    ),
                )
            for old, new in sorted(plan.rewrite.get(key, {}).items()):
                text = rewrite_iri(text, s.graph, old, new)
            for rule, triples in sorted(plan.add.get(key, {}).items()):
                text = append_triples(text, s.graph, rule, sorted(set(triples)))
        out.append(ogc.Source(s.module, s.kind, s.path, text))
    return out, plan


def Model_findings(m: ogc.Model) -> list[ogc.Finding]:
    ogc.check_isolated(m)
    return m.findings


def unified_patch(old: list[ogc.Source], new: list[ogc.Source]) -> dict[str, str]:
    """Per-repo unified diff (``git apply`` format), only for changed files."""
    per: dict[str, list[str]] = defaultdict(list)
    for a, b in zip(old, new, strict=True):
        if a.text != b.text:
            per[a.module].extend(
                difflib.unified_diff(
                    a.text.splitlines(keepends=True),
                    b.text.splitlines(keepends=True),
                    f"a/{a.path}",
                    f"b/{b.path}",
                )
            )
    return {k: "".join(v) for k, v in sorted(per.items())}


def summarize(base: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "before": base["summary"]["by_code"],
        "after": after["summary"]["by_code"],
        "total_before": base["summary"]["total"],
        "total_after": after["summary"]["total"],
    }


def run_fix(sources: list[ogc.Source], questions: list[dict[str, Any]], overrides: dict[str, Any]) -> dict[str, Any]:
    base = ogc.run(sources, questions, with_plan=False)
    new, plan = patch_sources(sources, overrides)
    after = ogc.run(new, questions, with_plan=False)
    patches = unified_patch(sources, new)
    files: dict[str, list[str]] = defaultdict(list)
    sizes: dict[str, int] = {}
    for a, b in zip(sources, new, strict=True):
        if a.text != b.text:
            files[a.module].append(a.path)
    for repo, patch in patches.items():
        sizes[repo] = sum(1 for ln in patch.splitlines() if ln[:1] in "+-" and ln[:3] not in ("+++", "---"))
    queue: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for q in sorted(plan.queue, key=lambda q: (q["repo"], q["rule"], q["subject"])):
        queue[q["repo"]][q["rule"]].append({k: v for k, v in q.items() if k not in ("repo", "rule")})
    repos = sorted({s.module for s in sources if s.kind == "pack"})
    return {
        "per_repo": {
            r: {
                "files_changed": sorted(files.get(r, [])),
                "rule_counts": {k: v for k, v in sorted(plan.counts.get(r, {}).items()) if v},
                "patch_lines": sizes.get(r, 0),
                "review_items": sum(len(v) for v in queue.get(r, {}).values()),
                "isolated_listed": len(plan.listed.get(r, [])),
            }
            for r in repos
        },
        "rule_totals": {rule: sum(plan.counts[r].get(rule, 0) for r in plan.counts) for rule in RULES},
        "findings": summarize(base, after),
        "review_queue": {r: dict(v) for r, v in sorted(queue.items())},
        "isolated_listed": {r: sorted(v) for r, v in sorted(plan.listed.items())},
        "patches": patches,
        "patched_sources": new,
    }


def write_outputs(result: dict[str, Any], out: Path) -> None:
    (out / "patches").mkdir(parents=True, exist_ok=True)
    for repo, patch in result["patches"].items():
        (out / "patches" / f"{repo}.patch").write_text(patch, encoding="utf-8")
    summary = {k: v for k, v in result.items() if k not in ("patches", "patched_sources", "review_queue")}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "review-queue.json").write_text(
        json.dumps(result["review_queue"], indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


class UnparseableOutput(ValueError):
    """A patched ``.ttl`` file does not re-parse, so nothing is written."""


def apply_to_dir(root: Path, old: list[ogc.Source], new: list[ogc.Source]) -> list[str]:
    """Write changed ``.ttl`` files into a pack checkout (not used by the fleet dry-run).

    Every changed file must re-parse as Turtle; otherwise nothing is written and ``UnparseableOutput`` is raised.
    """
    todo = [(a.path, b.text) for a, b in zip(old, new, strict=True) if a.text != b.text and a.path.endswith(".ttl")]
    bad = []
    for path, text in todo:
        try:
            Graph().parse(data=text, format="turtle")
        except Exception as exc:  # noqa: BLE001 - any parse failure blocks the write
            bad.append(f"{path}: {exc}")
    if bad:
        raise UnparseableOutput("refusing to write files that do not re-parse: " + "; ".join(bad))
    for path, text in todo:
        (root / path).write_text(text, encoding="utf-8")
    return [path for path, _ in todo]


def dir_sources(root: Path) -> list[ogc.Source]:
    """A pack checkout read from the working tree instead of a git ref."""
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if not p.is_file() or ".git/" in rel or ogc.is_fixture_path(rel):
            continue
        if ("/ontology/" in "/" + rel and rel.endswith(".ttl")) or rel.endswith("/" + ogc.DECLARATION):
            out.append(ogc.Source(module=root.name, kind="pack", path=rel, text=p.read_text(encoding="utf-8")))
    return out


def fix_pack(
    pack: Path,
    eg_repo: Path,
    ref: str = "origin/main",
    eg_extra_ref: str | None = None,
    overrides_path: Path | None = None,
    questions_path: Path | None = None,
    apply: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """Run the codemod over one pack checkout; write the patched .ttl files when ``apply``."""
    sources = ogc.eg_sources(eg_repo, ref, eg_extra_ref)
    pack_srcs = dir_sources(pack)
    questions = json.loads((questions_path or ogc.DEFAULT_CQ).read_text(encoding="utf-8"))["questions"]
    overrides = json.loads((overrides_path or DEFAULT_OVERRIDES).read_text(encoding="utf-8"))
    result = run_fix(sources + pack_srcs, questions, overrides)
    changed: list[str] = []
    if apply:
        new = [s for s in result["patched_sources"] if s.kind == "pack"]
        changed = apply_to_dir(pack, pack_srcs, new)
    return result, changed


__all__ = [
    "UnparseableOutput",
    "fix_pack",
    "run_fix",
    "patch_sources",
    "write_outputs",
    "dir_sources",
    "apply_to_dir",
    "BNode",
]
