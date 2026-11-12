"""connector-surface-audit: does a connector account for its whole MCP surface?

The connector surface standard (``reference/connector-surface.md``) names what
every connector must ship and serve, and this audit checks it from the
package alone. It reads one connector checkout, or every connector of a fleet
directory at a git ref in detached worktrees, and emits one record per
connector. It never imports the connector and never writes.

Each record lists its gaps under the part they belong to:

* ``entry-points``: one ``scion_sdk.connector`` entry point; no provider group
  the SDK replaced by convention and no plugin group outside the SDK namespace;
* ``tools``: one typed tool per upstream operation, none routed by ``action``;
* ``resources``: at least one declared data resource;
* ``prompts`` and ``skills``: packaged where the SDK serves them;
* ``served``: the package hands its content to the SDK;
* ``ontology``: packaged Turtle whose every class rolls up to a core class,
  with no ``owl:imports`` of the core ontology;
* ``contracts``, ``links`` and ``locations``: the three ontology parts, declared
  in ``<package>/connector_contracts.py`` (or typed in packaged Turtle).

The output is deterministic: sorted keys, sorted lists, no timestamps.
``--strict`` exits 1 when any connector has a gap; ``--markdown`` prints the
census table instead of JSON.
"""

from __future__ import annotations

from pipelines_hooks.core.ontology_base import CORE_ONTOLOGY

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

from pipelines_hooks.hygiene import connector_surface_contracts as contracts
from pipelines_hooks.hygiene import connector_surface_prompts as prompts
from pipelines_hooks.hygiene import connector_surface_tools as tools

PARENT_IRI = CORE_ONTOLOGY
CORE_NAMESPACE = PARENT_IRI + "#"
SDK_GROUP = "scion_sdk."
CONNECTOR_GROUP = SDK_GROUP + "connector"
#: Provider groups the SDK replaced by convention: a connector declares none of them.
REMOVED_GROUPS = tuple(SDK_GROUP + g for g in ("skill_providers", "ontology_providers", "source_connector_providers"))
_PROVIDER_SUFFIXES = ("skill_providers", "prompt_providers", "ontology_providers", "source_connector_providers")
_SERVED = re.compile(
    r"\bConnector\s*\(|\bConnectorContent\s*\(|register_connector_content\s*\(|register_ontology_resources\s*\("
)
_SKIP_DIRS = {"tests", "test", "scripts", "docs", "examples", ".venv", "build", "dist", "__pycache__"}
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
_OWL = "http://www.w3.org/2002/07/owl#"
_SUBCLASS = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
_CLASS_TYPES = {_OWL + "Class", "http://www.w3.org/2000/01/rdf-schema#Class"}
PARTS = (
    "entry-points",
    "tools",
    "resources",
    "prompts",
    "skills",
    "served",
    "ontology",
    "contracts",
    "links",
    "locations",
)


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


def _is_parent(term: str, parents: set[str]) -> bool:
    """A parent term: a declared core class, or any core-namespace class when none were given."""
    return term in parents if parents else term.startswith(CORE_NAMESPACE)


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
            if cls in linked or _is_parent(cls, parents):
                continue
            if any(_is_parent(up, parents) or up in linked for up in ups):
                linked.add(cls)
                changed = True
    redeclared = sorted(c for c in declared if _is_parent(c, parents))
    orphans = sorted(c for c in declared if c not in linked and not _is_parent(c, parents))
    return {
        "file": path.relative_to(root).as_posix(),
        "ontology_iris": headers,
        "imports": imports,
        "imports_parent": any(iri == PARENT_IRI or iri.startswith(PARENT_IRI + "/") for iri in imports),
        "classes": len(declared),
        "linked": len(linked),
        "redeclared_parent_terms": len(redeclared),
        "orphans": orphans,
        "triples": doc.triples,
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
    for value in points.get(CONNECTOR_GROUP, {}).values():
        return _module_dir(root, value.split(".")[0])
    for name, group_points in points.items():
        if name.endswith(_PROVIDER_SUFFIXES):
            for value in group_points.values():
                return _module_dir(root, value.split(".")[0])
    guess = root / root.name.replace("-", "_")
    return guess if guess.is_dir() else None


def _entry_point_gaps(points: dict[str, dict[str, str]]) -> tuple[list[str], list[str]]:
    gaps = []
    if len(points.get(CONNECTOR_GROUP, {})) != 1:
        gaps.append(f"entry-points: declare exactly one {CONNECTOR_GROUP} entry point")
    removed = sorted(g for g in points if g in REMOVED_GROUPS)
    if removed:
        gaps.append("entry-points: remove provider groups (the SDK finds content by convention): " + ", ".join(removed))
    foreign = sorted(g for g in points if g.endswith(_PROVIDER_SUFFIXES) and not g.startswith(SDK_GROUP))
    if foreign:
        gaps.append("entry-points: plugin group outside the SDK namespace: " + ", ".join(foreign))
    return gaps, foreign


@dataclass
class _Content:
    """The packaged content of one connector."""

    skills: list[Path] = field(default_factory=list)
    prompts: list[Path] = field(default_factory=list)
    ontologies: list[Path] = field(default_factory=list)
    shapes: list[Path] = field(default_factory=list)
    stray_skills: list[str] = field(default_factory=list)

    @classmethod
    def read(cls, root: Path, pkg: Path | None) -> _Content:
        def files(sub: str, pattern: str) -> list[Path]:
            return sorted((pkg / sub).glob(pattern)) if pkg else []

        skills = files("skills", "*/SKILL.md")
        stray = sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("SKILL.md")
            if not _SKIP_DIRS.intersection(p.relative_to(root).parts) and p not in skills
        )
        return cls(
            skills=skills,
            prompts=[p for p in files("prompts", "*.json") if not p.name.startswith("_")],
            ontologies=files("ontology", "*.ttl"),
            shapes=files("ontology/shapes", "*.ttl"),
            stray_skills=stray,
        )

    def counts(self) -> dict[str, int]:
        return {
            "skills": len(self.skills),
            "prompts": len(self.prompts),
            "prompts_valid": sum(_prompt_ok(p) for p in self.prompts),
            "ontology": len(self.ontologies),
            "shapes": len(self.shapes),
        }


def _content_gaps(content: _Content, counts: dict[str, int], served: bool) -> list[str]:
    gaps = []
    if not counts["prompts"]:
        gaps.append("prompts: no packaged prompt (<package>/prompts/<name>.json)")
    elif counts["prompts_valid"] < counts["prompts"]:
        gaps.append(
            f"prompts: {counts['prompts'] - counts['prompts_valid']} prompt file(s) without instructions.core_directive"
        )
    if not counts["skills"]:
        gaps.append("skills: no packaged skill (<package>/skills/<name>/SKILL.md)")
    if content.stray_skills:
        gaps.append(f"skills: {len(content.stray_skills)} SKILL.md outside <package>/skills (never served)")
    if not served:
        gaps.append(
            "served: the package does not hand its content to the SDK (no Connector(...) or content registration)"
        )
    return gaps


def _ontology_gaps(reports: list[dict[str, Any]]) -> list[str]:
    if not reports:
        return ["ontology: no packaged ontology (<package>/ontology/*.ttl)"]
    gaps = []
    for report in reports:
        if report["orphans"]:
            names = ", ".join(o.rsplit("#", 1)[-1].rsplit("/", 1)[-1] for o in report["orphans"])
            count = len(report["orphans"])
            gaps.append(f"ontology: {report['file']}: {count} class(es) do not roll up to a core class: {names}")
        if report["imports_parent"]:
            gaps.append(f"ontology: {report['file']}: owl:imports of the core ontology (extend core classes instead)")
    if not any(r["classes"] for r in reports):
        gaps.append("ontology: no class declared")
    return gaps


def _declared(pkg: Path | None, reports: list[dict[str, Any]]) -> contracts.Declared:
    declared = contracts.Declared()
    if pkg is not None and (pkg / contracts.CONTRACTS_MODULE).is_file():
        contracts.read_module(pkg / contracts.CONTRACTS_MODULE, declared)
    for report in reports:
        contracts.read_turtle(report["triples"], report["file"], declared)
    return declared


def _unmentioned(tool_names: list[str], content: _Content) -> list[str]:
    """``skills`` gap: tools that no packaged skill or prompt names in its text."""
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in [*content.skills, *content.prompts])
    missing = [t for t in tool_names if not re.search(rf"(?<![\w]){re.escape(t)}(?![\w])", text)]
    if not missing:
        return []
    return [f"skills: {len(missing)} tool(s) no packaged skill or prompt names: {', '.join(missing)}"]


def _linked_prompts(declared: contracts.Declared) -> set[str]:
    named = {p for link in declared.links for p in link.get("prompts") or [] if isinstance(p, str)}
    for link in declared.links:
        named |= {n.rsplit(":prompt:", 1)[-1] for n in link.get("names") or [] if ":prompt:" in n}
    return named


def _routes_action(declared: contracts.Declared, name: str) -> bool:
    for entry in declared.upstream_tools:
        schema = entry.get("input_schema")
        if contracts.upstream_name(entry) == name and isinstance(schema, dict):
            props = schema.get("properties")
            return isinstance(props, dict) and bool(set(props) & tools.ROUTING_PARAMETERS)
    return False


def audit_connector(root: Path, parents: set[str] | None = None, served: list[Any] | None = None) -> dict[str, Any]:
    """The surface record of the connector checkout at ``root``.

    ``served`` holds the tools the built server registers (``served_tools``); when given they replace the
    static tool read, so SDK-derived tools count and an ``action`` input property marks a routed tool.
    """
    parents = parents or set()
    pyproject = root / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8")) if pyproject.is_file() else {}
    points = _entry_points(project)
    connector = (sorted(points.get(CONNECTOR_GROUP, {})) or [root.name])[0]
    package = _package_root(root, points)
    pkg = package if package is not None and package.is_dir() else None
    content = _Content.read(root, pkg)
    sources = list(_python_sources(pkg)) if pkg else []
    content_served = any(_SERVED.search(p.read_text(encoding="utf-8", errors="replace")) for p in sources)
    surface = tools.scan(sources, root)
    tool_names = tools.tool_names(surface, connector)
    if served is not None:
        tool_names = sorted(t.name for t in served)
        surface.decorated_tools, surface.derived_tools = tool_names, bool(tool_names)
        surface.routed_tools = sorted(
            f"{t.name} (served)" for t in served if set(t.properties) & tools.ROUTING_PARAMETERS
        )
    reports = [ontology_report(p, root, parents) for p in content.ontologies]
    declared = _declared(pkg, reports)
    upstream = contracts.upstream_names(declared)
    registered = set(tool_names)
    # A proxy connector registers no tool offline: its declared upstream tools count as served.
    tool_names = sorted(set(tool_names) | set(upstream))
    surface.decorated_tools = sorted(set(surface.decorated_tools) | set(upstream))
    surface.routed_tools = sorted(
        {*surface.routed_tools, *(f"{n} (declared)" for n in upstream if _routes_action(declared, n))}
    )
    counts = content.counts()
    skill_names = [p.parent.name for p in content.skills]
    known = prompts.Known(
        contract_tools=contracts.contract_tools(declared),
        skills=set(skill_names),
        locations=contracts.location_names(declared),
        linked=_linked_prompts(declared),
    )
    prompt_gaps, agents = prompts.prompt_gaps(content.prompts, contracts.role_names(declared), known)
    entry_gaps, foreign = _entry_point_gaps(points)
    gaps = [
        *entry_gaps,
        *tools.tool_gaps(surface),
        *contracts.upstream_gaps(declared, registered),
        *tools.resource_gaps(surface),
        *_content_gaps(content, counts, content_served),
        *prompt_gaps,
        *_ontology_gaps(reports),
        *contracts.contract_gaps(declared),
        *contracts.link_gaps(declared, [p.stem for p in content.prompts], skill_names),
        *contracts.location_gaps(declared),
        *contracts.tool_coverage_gaps(declared, tool_names),
        *_unmentioned(tool_names, content),
    ]
    for report in reports:
        del report["triples"]
    return {
        "connector": connector,
        "repository": root.name,
        "package": pkg.relative_to(root).as_posix() if pkg else None,
        "entry_points": {g: sorted(v) for g, v in points.items() if g.startswith(SDK_GROUP)},
        "foreign_entry_point_groups": foreign,
        "counts": counts,
        "tools": {
            "names": tool_names,
            "decorated": len(surface.decorated_tools),
            "derived": surface.derived_tools,
            "routed": surface.routed_tools,
            "source": "served" if served is not None else "static",
            "upstream": upstream,
        },
        "resources": surface.resources,
        "prompts": agents,
        "skills": skill_names,
        "declarations": {
            "contracts": len(declared.contracts),
            "links": len(declared.links),
            "locations": len(declared.locations),
            "roles": len(declared.roles),
            "sources": sorted(set(declared.sources)),
        },
        "stray_skills": content.stray_skills,
        "served": content_served,
        "ontology": reports,
        "parent_linked": bool(reports) and not any(r["orphans"] or r["imports_parent"] for r in reports),
        "missing": sorted({gap.split(":", 1)[0] for gap in gaps}, key=PARTS.index),
        "gaps": gaps,
        "complete": not gaps,
    }


# ── a fleet at a ref, in detached worktrees ─────────────────────────────────


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def _export(repo: Path, ref: str, tree: Path) -> str | None:
    """Write the files of ``repo`` at ``ref`` under ``tree``; the error text, or ``None``.

    ``git archive`` reads objects only, so a shared checkout keeps its worktrees,
    index and refs unchanged.
    """
    archive = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", ref], capture_output=True, check=False)
    if archive.returncode:
        return archive.stderr.decode(errors="replace").strip()[:200]
    tree.mkdir(parents=True)
    unpacked = subprocess.run(["tar", "-x", "-C", str(tree)], input=archive.stdout, capture_output=True, check=False)
    return unpacked.stderr.decode(errors="replace").strip()[:200] if unpacked.returncode else None


def audit_fleet(
    fleet: Path, ref: str, parents: set[str], exclude: Iterable[str] = (), only: Iterable[str] = ()
) -> list[dict[str, Any]]:
    """Audit every git repository under ``fleet`` at ``ref``, read through ``git archive``."""
    skip, wanted = set(exclude), set(only)
    records = []
    for repo in sorted(p for p in fleet.iterdir() if (p / ".git").exists() and p.name not in skip):
        if wanted and repo.name not in wanted:
            continue
        with tempfile.TemporaryDirectory(prefix=f"csa-{repo.name}-") as tmp:
            tree = Path(tmp) / repo.name
            error = _export(repo, ref, tree)
            if error is not None:
                gap = f"entry-points: cannot read {ref}: {error}"
                records.append(
                    {
                        "repository": repo.name,
                        "connector": repo.name,
                        "complete": False,
                        "gaps": [gap],
                        "missing": ["entry-points"],
                    }
                )
                continue
            record = audit_connector(tree, parents)
            record["ref"] = _git(repo, "rev-parse", "--short", ref).stdout.strip()
            records.append(record)
    return records


def _connector_section(record: dict[str, Any]) -> list[str]:
    verdict = "PASS" if record["complete"] else "FAIL"
    lines = [f"### {record['repository']} — {verdict}", ""]
    if record.get("ref"):
        lines += [f"Ref `{record['ref']}`. Tools (static): {len(record.get('tools', {}).get('names', []))}.", ""]
    for part in PARTS:
        items = [g.split(": ", 1)[1] for g in record["gaps"] if g.split(":", 1)[0] == part]
        lines += [f"- [ ] **{part}**: {item}" for item in items]
    return [*lines, ""]


def markdown(records: list[dict[str, Any]]) -> str:
    """The census: totals, missing parts per connector, then one fix checklist per connector."""
    ordered = sorted(records, key=lambda r: r["repository"])
    passed = sum(bool(r["complete"]) for r in records)
    lines = [
        f"Connectors: {len(records)}. Pass: {passed}. Fail: {len(records) - passed}.",
        "",
        "| Part | Connectors missing it |",
        "|---|---|",
        *(f"| {part} | {sum(part in r.get('missing', []) for r in records)} |" for part in PARTS),
        "",
        "| Connector | Verdict | Gaps | Missing parts |",
        "|---|---|---|---|",
    ]
    for record in ordered:
        verdict = "PASS" if record["complete"] else "FAIL"
        lines.append(
            f"| {record['repository']} | {verdict} | {len(record['gaps'])} | {', '.join(record.get('missing', [])) or '-'} |"
        )
    lines += ["", "## Fix checklists", ""]
    for record in ordered:
        if not record["complete"]:
            lines += _connector_section(record)
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-surface-audit", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="one connector checkout")
    parser.add_argument("--fleet", type=Path, help="a directory of connector repositories")
    parser.add_argument("--ref", default="origin/main", help="ref audited in --fleet mode")
    parser.add_argument("--exclude", action="append", default=[], help="repository to skip in --fleet mode")
    parser.add_argument("--only", action="append", default=[], help="audit only this repository in --fleet mode")
    parser.add_argument("--parent-ontology", type=Path, help="directory of the core ontology *.ttl files")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any connector has a gap")
    parser.add_argument("--markdown", action="store_true", help="print the census table instead of JSON")
    arguments = parser.parse_args(argv)
    parents = parent_terms(arguments.parent_ontology)
    records = (
        audit_fleet(arguments.fleet, arguments.ref, parents, arguments.exclude, arguments.only)
        if arguments.fleet
        else [audit_connector(arguments.root, parents)]
    )
    if arguments.markdown:
        print(markdown(records), end="")
    else:
        print(
            json.dumps(
                {"parent_iri": PARENT_IRI, "parent_terms": len(parents), "connectors": records},
                indent=2,
                sort_keys=True,
            )
        )
    return 1 if arguments.strict and not all(r["complete"] for r in records) else 0
