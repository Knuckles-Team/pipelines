"""connector-surface-audit: does a connector ship and serve all five surfaces?

A connector serves five surfaces: tools, prompts, skills, resources and its
ontology. The ontology joins the epistemic-graph parent ontology rather than
standing alone. This audit reads one connector checkout, or every connector of
a fleet directory at a git ref, and emits one JSON record per connector.

Static levels, read from the checkout only:

* ``entry_points``: the ``agent_connector_sdk.connector``, ``skill_providers``,
  ``prompt_providers``, ``ontology_providers`` and ``source_connector_providers``
  groups, and any plugin group still outside the SDK namespace;
* ``files``: ``skills/<name>/SKILL.md``, ``prompts/<name>.json`` with an
  ``instructions.core_directive``, ``ontology/*.ttl`` and ``ontology/shapes/*.ttl``;
* ``pack``: whether the files sit where the SDK content registration and pack
  builder read them (``<package>/skills``, ``<package>/prompts``,
  ``<package>/ontology``);
* ``served``: whether the server source hands the content to the SDK
  (``create_mcp_server(content=...)``, ``register_connector_content`` or
  ``register_ontology_resources``). Without it the files exist but no MCP
  listing serves them, so the pack captured from the live server lacks them;
* ``ontology``: per Turtle file, the ``owl:Ontology`` header, ``owl:imports`` of
  the parent IRI, and each declared class classified as a parent term, linked
  (a direct or transitive ``rdfs:subClassOf`` reaching a parent term) or orphan.

The audit never writes. The result is deterministic for one tree: sorted keys,
sorted lists, no timestamps. ``--strict`` exits 1 when any connector is
incomplete; the default only reports.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PARENT_IRI = "http://knuckles.team/kg"
SDK_GROUP = "agent_connector_sdk."
GROUPS = ("connector", "skill_providers", "prompt_providers", "ontology_providers", "source_connector_providers")
_SERVED = re.compile(r"\bConnectorContent\s*\(|register_connector_content\s*\(|register_ontology_resources\s*\(")
_SKIP_DIRS = {"tests", "test", "scripts", "docs", "examples", ".venv", "build", "dist", "__pycache__"}
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
_OWL = "http://www.w3.org/2002/07/owl#"
_SUBCLASS = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
_CLASS_TYPES = {_OWL + "Class", "http://www.w3.org/2000/01/rdf-schema#Class"}


# ── a small Turtle reader: enough for headers, classes and subclass edges ────

_STRING = re.compile(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')
_COMMENT = re.compile(r"(?m)#[^\n]*$")
_IRI = re.compile(r"<([^<>\s]*)>")
_PREFIX = re.compile(r"(?im)^\s*@?prefix\s+([A-Za-z][\w.-]*)?:\s+\x00(\d+)\s*\.?")
_TERMINATOR = re.compile(r"\s\.(?=\s|$)|(?<=[\]>)\w\"'])\.(?=\s|$)")


@dataclass
class Turtle:
    """Triples of one Turtle document, with IRIs expanded."""

    triples: list[tuple[str, str, str]] = field(default_factory=list)

    def subjects(self, predicate: str, objects: set[str]) -> set[str]:
        return {s for s, p, o in self.triples if p == predicate and o in objects}

    def objects(self, subject: str | None, predicate: str) -> set[str]:
        return {o for s, p, o in self.triples if p == predicate and (subject is None or s == subject)}


def _expand(token: str, prefixes: dict[str, str], iris: list[str]) -> str:
    if token.startswith("\x00"):
        return iris[int(token[1:]) - 1]
    if token == "a":
        return _RDF_TYPE
    prefix, sep, local = token.partition(":")
    if sep and prefix in prefixes:
        return prefixes[prefix] + local
    return token


def parse_turtle(text: str) -> Turtle:
    """Parse the subject/predicate/object structure of ``text``.

    Literals and blank-node bodies are kept as opaque tokens; only IRIs and
    prefixed names are expanded. Good for header, class and subclass reads.
    """
    iris: list[str] = []

    def keep(match: re.Match[str]) -> str:
        iris.append(match.group(1))
        return f" \x00{len(iris)} "

    # Strings first (they may hold '#' or '<'), then IRIs (they hold '#'), then comments.
    body = _STRING.sub(' "" ', text)
    body = _IRI.sub(keep, body)
    body = _COMMENT.sub("", body)
    prefixes = {(m.group(1) or ""): iris[int(m.group(2)) - 1] for m in _PREFIX.finditer(body)}
    body = _PREFIX.sub("", body)
    body = re.sub(r"\[[^\[\]]*\]", " _:b ", body)
    doc = Turtle()
    for statement in _TERMINATOR.split(body):
        tokens = statement.replace(";", " ; ").replace(",", " , ").split()
        if len(tokens) < 3:
            continue
        subject = _expand(tokens[0], prefixes, iris)
        predicate: str | None = None
        expect_predicate = True
        for token in tokens[1:]:
            if token == ";":
                expect_predicate = True
                continue
            if token == ",":
                continue
            if expect_predicate:
                predicate = _expand(token, prefixes, iris)
                expect_predicate = False
                continue
            if predicate is not None:
                doc.triples.append((subject, predicate, _expand(token, prefixes, iris)))
    return doc


def classes(doc: Turtle) -> set[str]:
    return doc.subjects(_RDF_TYPE, _CLASS_TYPES)


def parent_terms(parent_dir: Path | None) -> set[str]:
    """Every class the parent ontology declares (``*.ttl`` under ``parent_dir``)."""
    if parent_dir is None:
        return set()
    terms: set[str] = set()
    for path in sorted(parent_dir.glob("*.ttl")):
        terms |= classes(parse_turtle(path.read_text(encoding="utf-8", errors="replace")))
    return terms


def ontology_report(path: Path, root: Path, parents: set[str]) -> dict[str, Any]:
    doc = parse_turtle(path.read_text(encoding="utf-8", errors="replace"))
    declared = classes(doc)
    headers = sorted(doc.subjects(_RDF_TYPE, {_OWL + "Ontology"}))
    imports = sorted(doc.objects(None, _OWL + "imports"))
    supers = {c: doc.objects(c, _SUBCLASS) for c in declared}
    linked: set[str] = set()
    changed = True
    while changed:
        changed = False
        for cls, ups in supers.items():
            if cls not in linked and cls not in parents and ups & (parents | linked):
                linked.add(cls)
                changed = True
    redeclared = sorted(declared & parents)
    orphans = sorted(declared - parents - linked)
    return {
        "file": path.relative_to(root).as_posix(),
        "ontology_iris": headers,
        "imports": imports,
        "imports_parent": any(iri == PARENT_IRI or iri.startswith(PARENT_IRI + "/") for iri in imports),
        "classes": len(declared),
        "linked": len(linked),
        "redeclared_parent_terms": len(redeclared),
        "orphans": orphans,
    }


# ── one connector ────────────────────────────────────────────────────────────


def _entry_points(project: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw = project.get("project", {}).get("entry-points", {}) or {}
    return {group: dict(sorted(points.items())) for group, points in sorted(raw.items()) if isinstance(points, dict)}


def _module_dir(root: Path, module: str) -> Path:
    return root.joinpath(*module.split(":")[0].split("."))


def _python_sources(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if not _SKIP_DIRS.intersection(path.relative_to(root).parts[:-1]) and not path.name.startswith("test_"):
            yield path


def _prompt_ok(path: Path) -> bool:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    directive = (document.get("instructions") or {}).get("core_directive") if isinstance(document, dict) else None
    return isinstance(directive, str) and bool(directive.strip())


def _package_root(root: Path, points: dict[str, dict[str, str]]) -> Path | None:
    for group in ("connector", "ontology_providers", "skill_providers", "prompt_providers"):
        for value in points.get(SDK_GROUP + group, {}).values():
            return _module_dir(root, value.split(".")[0])
    for name, group_points in points.items():
        if name.endswith(GROUPS[1:]):
            for value in group_points.values():
                return _module_dir(root, value.split(".")[0])
    guess = root / root.name.replace("-", "_")
    return guess if guess.is_dir() else None


def audit_connector(root: Path, parents: set[str] | None = None) -> dict[str, Any]:
    """The static surface record of the connector checkout at ``root``."""
    parents = parents or set()
    pyproject = root / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8")) if pyproject.is_file() else {}
    points = _entry_points(project)
    sdk_points = {g: sorted(points.get(SDK_GROUP + g, {})) for g in GROUPS}
    foreign = sorted(g for g in points if g.endswith(GROUPS[1:]) and not g.startswith(SDK_GROUP))
    package = _package_root(root, points)
    pkg = package if package is not None and package.is_dir() else None

    def files(sub: str, pattern: str) -> list[Path]:
        return sorted((pkg / sub).glob(pattern)) if pkg else []

    skills = files("skills", "*/SKILL.md")
    prompt_files = [p for p in files("prompts", "*.json") if not p.name.startswith("_")]
    ontologies = files("ontology", "*.ttl")
    shapes = files("ontology/shapes", "*.ttl")
    stray_skills = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("SKILL.md")
        if not _SKIP_DIRS.intersection(p.relative_to(root).parts) and p not in skills
    )
    served = any(
        _SERVED.search(p.read_text(encoding="utf-8", errors="replace")) for p in (_python_sources(pkg) if pkg else ())
    )
    reports = [ontology_report(p, root, parents) for p in ontologies]
    domain = [r for r in reports if r["classes"]]
    parent_linked = bool(domain) and all(r["imports_parent"] and not r["orphans"] for r in domain)
    counts = {
        "skills": len(skills),
        "prompts": len(prompt_files),
        "prompts_valid": sum(_prompt_ok(p) for p in prompt_files),
        "ontology": len(ontologies),
        "shapes": len(shapes),
    }
    gaps = []
    for group in GROUPS[:4]:
        if not sdk_points[group]:
            gaps.append(f"no {SDK_GROUP}{group} entry point")
    if foreign:
        gaps.append("plugin group outside the SDK namespace: " + ", ".join(foreign))
    for kind in ("skills", "prompts", "ontology"):
        if not counts[kind]:
            gaps.append(f"no packaged {kind}")
    if counts["prompts_valid"] < counts["prompts"]:
        gaps.append(f"{counts['prompts'] - counts['prompts_valid']} prompt file(s) without instructions.core_directive")
    if stray_skills:
        gaps.append(f"{len(stray_skills)} SKILL.md outside <package>/skills (pack never reads them)")
    if not served:
        gaps.append("server does not register connector content (skills/prompts/ontology not served over MCP)")
    if ontologies and not parent_linked:
        gaps.append("ontology not linked to the parent ontology")
    return {
        "connector": (sdk_points["connector"] or [root.name])[0],
        "repository": root.name,
        "package": pkg.relative_to(root).as_posix() if pkg else None,
        "entry_points": sdk_points,
        "foreign_entry_point_groups": foreign,
        "counts": counts,
        "stray_skills": stray_skills,
        "served": served,
        "pack_complete": served and all(counts[k] for k in ("skills", "prompts", "ontology")) and not stray_skills,
        "ontology": reports,
        "parent_linked": parent_linked,
        "gaps": gaps,
        "complete": not gaps,
    }


# ── a fleet at a ref, in detached worktrees ─────────────────────────────────


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def audit_fleet(fleet: Path, ref: str, parents: set[str], exclude: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Audit every git repository under ``fleet`` at ``ref`` in a detached worktree."""
    skip = set(exclude)
    records = []
    for repo in sorted(p for p in fleet.iterdir() if (p / ".git").exists() and p.name not in skip):
        with tempfile.TemporaryDirectory(prefix=f"csa-{repo.name}-") as tmp:
            tree = Path(tmp) / repo.name
            added = _git(repo, "worktree", "add", "--detach", "--quiet", str(tree), ref)
            if added.returncode:
                records.append(
                    {
                        "repository": repo.name,
                        "connector": repo.name,
                        "error": added.stderr.strip()[:200],
                        "complete": False,
                        "gaps": [f"cannot check out {ref}"],
                    }
                )
                continue
            try:
                record = audit_connector(tree, parents)
                record["ref"] = _git(tree, "rev-parse", "--short", "HEAD").stdout.strip()
                records.append(record)
            finally:
                _git(repo, "worktree", "remove", "--force", str(tree))
    return records


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-surface-audit", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="one connector checkout")
    parser.add_argument("--fleet", type=Path, help="a directory of connector repositories")
    parser.add_argument("--ref", default="origin/main", help="ref audited in --fleet mode")
    parser.add_argument("--exclude", action="append", default=[], help="repository to skip in --fleet mode")
    parser.add_argument("--parent-ontology", type=Path, help="directory of the parent ontology *.ttl files")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any connector is incomplete")
    arguments = parser.parse_args(argv)
    parents = parent_terms(arguments.parent_ontology)
    records = (
        audit_fleet(arguments.fleet, arguments.ref, parents, arguments.exclude)
        if arguments.fleet
        else [audit_connector(arguments.root, parents)]
    )
    print(
        json.dumps(
            {"parent_iri": PARENT_IRI, "parent_terms": len(parents), "connectors": records}, indent=2, sort_keys=True
        )
    )
    return 1 if arguments.strict and not all(r["complete"] for r in records) else 0
