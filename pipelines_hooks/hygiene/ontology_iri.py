"""ontology-iri: every custom ontology IRI lives under the one ontology base.

Constitution Article XXXIII and ``reference/spec-standard.md`` (section "Ontology
IRIs"). The one base is ``https://knuckles-team.github.io/ontology/<module>#``:
HTTPS, versionless, with modules named for the domain they cover. The gate fails
any tracked file that holds

* a custom namespace or ontology IRI that is not under the base,
* an ``http://`` custom namespace,
* a module path segment equal to a product, repository or connector-package name,
* a versioned namespace (versions belong in ``owl:versionIRI`` only).

Standard vocabularies (W3C, Dublin Core, schema.org, FIBO, OGC, ...) and
documentation hosts are allowed through ``ALLOWED_HOSTS``. Reserved example hosts
are allowed under test and fixture paths only. The product-name list is the
built-in core names plus every repository name in the workspace manifest when one
is found (``--workspace``, ``ONTOLOGY_IRI_WORKSPACE`` or a parent directory).
The gate is blocking: any finding exits 1.
"""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.ontology_base import BASE
from pipelines_hooks.core.tracked import SKIP_DIRECTORIES, tracked_paths


#: Core product and repository names that never appear as an IRI path segment.
CORE_PRODUCT_NAMES = frozenset(
    {
        "medulla", "arbora", "scion-sdk", "scion", "meristem", "overstory", "tuig", "axil", "pipelines",
        "universal-skills", "agent-utilities", "agent-connector-sdk", "agent-webui", "epistemic-graph",
        "graph-os", "genius-bot", "geniusbot", "skill-graphs", "repository-manager", "systems-manager",
        "craft-suite", "craft-suite-api", "artcraft", "agent-packages",
    }
)  # fmt: skip
#: Product abbreviations that never appear as a path or fragment token.
PRODUCT_ABBREVIATIONS = frozenset({"au", "eg"})
#: A segment ending in one of these is a connector package name.
PACKAGE_SUFFIXES = ("-mcp", "-agent", "-api", "-sdk")

#: Hosts of standard vocabularies, standards bodies and documentation. Never custom namespaces.
ALLOWED_HOSTS = frozenset(
    {
        "www.w3.org", "w3.org", "w3id.org", "purl.org", "purl.obolibrary.org", "purl.archive.org", "schema.org",
        "xmlns.com", "spec.edmcouncil.org", "www.opengis.net", "opengis.net", "www.omg.org", "omg.org",
        "dublincore.org", "www.wikidata.org", "wikidata.org", "dbpedia.org", "datashapes.org", "www.geonames.org",
        "sws.geonames.org", "www.openarchives.org", "spdx.org", "qudt.org", "www.qudt.org", "vocab.org",
        "www.ontologydesignpatterns.org", "ontologydesignpatterns.org", "www.ebu.ch", "rdfs.org",
        "schemas.openxmlformats.org", "schemas.microsoft.com", "schemas.xmlsoap.org", "www.sitemaps.org",
        "ietf.org", "datatracker.ietf.org", "www.iana.org", "json-schema.org", "spec.openapis.org",
        "modelcontextprotocol.io", "a2a-protocol.org", "github.com", "raw.githubusercontent.com", "gitlab.com",
        "doi.org", "arxiv.org", "www.apache.org", "apache.org", "www.gnu.org", "opensource.org",
        "creativecommons.org", "docs.python.org", "pypi.org", "crates.io", "docs.rs",
    }
)  # fmt: skip
#: Reserved example hosts: allowed under test and fixture paths only.
EXAMPLE_HOST = re.compile(r"(^|\.)example(\.(com|org|net))?$|\.(invalid|test|example)$|^localhost$|^127\.|^0\.0\.0\.0$")
#: Hosts of retired custom namespaces, flagged wherever they appear in a tracked text file.
LEGACY_HOST = re.compile(
    r"""https?://(?:[\w.-]*knuckles\.team|medulla|epistemic-graph|[\w.-]*agent-utilities\.dev|graph-os)(?=[/#"'<>\s]|$)"""
)

RDF_SUFFIXES = frozenset({".ttl", ".trig", ".nt", ".nq", ".n3", ".owl", ".rdf", ".jsonld", ".rq", ".sparql", ".shacl"})
TEXT_SUFFIXES = RDF_SUFFIXES | frozenset(
    {
        ".py",
        ".rs",
        ".go",
        ".ts",
        ".tsx",
        ".js",
        ".json",
        ".yml",
        ".yaml",
        ".toml",
        ".md",
        ".txt",
        ".xml",
        ".sql",
        ".java",
    }
)
SKIP_FILES = frozenset({"uv.lock", "Cargo.lock", "package-lock.json", "pnpm-lock.yaml", "go.sum", "poetry.lock"})
MAX_BYTES = 2_000_000

PREFIX_DECL = re.compile(r"(?:@prefix|PREFIX|prefix)\s+[\w.-]*:\s*<([^>\s]+)>")
BASE_DECL = re.compile(r"(?:@base|BASE)\s*<([^>\s]+)>")
XMLNS_DECL = re.compile(r"""xmlns(?::[\w.-]+)?\s*=\s*["']([^"']+)["']|xml:base\s*=\s*["']([^"']+)["']""")
ANGLE_IRI = re.compile(r"<(https?://[^>\s]+)>")
CONSTANT = re.compile(
    r"""\b\w*(?:NS|NAMESPACE|IRI|ONTOLOGY|PREFIX)\w*\s*(?::[^=\n]*)?[=:]\s*[rb]?["'](https?://[^"'\s]+)["']"""
)
LEGACY_LITERAL = re.compile(r"""(https?://[^"'<>\s)\]`,;]+)""")
VERSION_SEGMENT = re.compile(r"^(?:v\d+(?:[._-]\d+)*|\d+(?:[._-]\d+)+|\d{4}-\d{2}-\d{2}|.+[-_]v\d+(?:[._]\d+)*)$", re.I)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    iri: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.iri}"


def workspace_names(workspace: Path | None) -> frozenset[str]:
    """Product repository names from a workspace manifest: the basename of each GitHub repository URL.

    Service and image repositories on the private host are named after the upstream system they
    package (the very system a ``connector/<system>`` module names), so they are not product names.
    """
    if workspace is None or not workspace.is_file():
        return frozenset()
    names = set()
    for line in workspace.read_text(encoding="utf-8").splitlines():
        match = re.search(r"url:\s*https://github\.com/[^/\s]+/([^/\s]+?)(?:\.git)?\s*$", line)
        if match:
            names.add(match.group(1).lower())
    return frozenset(names)


def find_workspace(start: Path, explicit: Path | None) -> Path | None:
    candidate = explicit or (
        Path(os.environ["ONTOLOGY_IRI_WORKSPACE"]) if os.environ.get("ONTOLOGY_IRI_WORKSPACE") else None
    )
    if candidate:
        return candidate
    for parent in [start, *start.parents][:8]:
        if (parent / "workspace.yml").is_file():
            return parent / "workspace.yml"
    return None


def _product_segment(segment: str, names: frozenset[str]) -> bool:
    """A segment is a product when it, or any run of its hyphen tokens, is a product name or abbreviation."""
    lowered = segment.lower()
    if lowered in names or lowered in PRODUCT_ABBREVIATIONS or lowered.endswith(PACKAGE_SUFFIXES):
        return True
    tokens = re.split(r"[-_.]", lowered)
    if any(token in PRODUCT_ABBREVIATIONS for token in tokens):
        return True
    runs = {"-".join(tokens[i:j]) for i in range(len(tokens)) for j in range(i + 1, len(tokens) + 1)}
    return bool(runs & names)


def judge(iri: str, names: frozenset[str], *, example_ok: bool, versioned_ok: bool = False) -> str | None:
    """The reason an IRI breaks the standard, or None when it is allowed."""
    match = re.match(r"(https?)://([^/#?]+)([^#?]*)", iri)
    if not match:
        return None
    scheme, host, path = match.groups()
    host = host.lower()
    if host in ALLOWED_HOSTS:
        return None
    if example_ok and EXAMPLE_HOST.search(host):
        return None
    if not iri.startswith(BASE):
        return "http-namespace" if scheme == "http" else "outside-base"
    segments = [part for part in path[len("/ontology/") :].split("/") if part]
    if not segments:
        return "outside-base"
    fragment = iri.partition("#")[2]
    if any(part.lower() in PRODUCT_ABBREVIATIONS for part in re.split(r"[/.]", fragment)):
        return "product-abbreviation-token"
    for segment in segments:
        if _product_segment(segment, names):
            return "product-name-segment"
    if not versioned_ok and any(VERSION_SEGMENT.match(segment) for segment in segments):
        return "versioned-namespace"
    return None


def _candidates(path: Path, text: str) -> Iterable[tuple[int, str, bool]]:
    """(line, iri, versioned_ok) for every namespace-bearing IRI in one file."""
    rdf = path.suffix in RDF_SUFFIXES
    for number, line in enumerate(text.splitlines(), 1):
        version_line = "versionIRI" in line
        seen: set[str] = set()
        patterns = [PREFIX_DECL, BASE_DECL, CONSTANT]
        for pattern in patterns:
            for match in pattern.finditer(line):
                seen.add(match.group(1))
        for match in XMLNS_DECL.finditer(line):
            seen.add(match.group(1) or match.group(2))
        if rdf:
            seen.update(ANGLE_IRI.findall(line))
        for match in LEGACY_LITERAL.finditer(line):
            if LEGACY_HOST.match(match.group(1)):
                seen.add(match.group(1))
        for iri in seen:
            yield number, iri, version_line


def _is_test_path(relative: str) -> bool:
    parts = relative.split("/")
    return any(part in {"tests", "test", "fixtures", "testdata"} for part in parts[:-1]) or parts[-1].startswith(
        "test_"
    )


def scan(root: Path, names: frozenset[str], only: frozenset[str] | None = None) -> list[Finding]:
    """Scan the tracked files under ``root``; ``only`` limits it to those repository-relative paths."""
    root = root.resolve()
    repository = repo_root(root)
    findings: list[Finding] = []
    for relative in tracked_paths(repository, preserve_index=False):
        if only is not None and relative not in only:
            continue
        path = repository / relative
        if not path.is_relative_to(root) or path.suffix not in TEXT_SUFFIXES or path.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRECTORIES or part in {"target", ".mypy_cache"} for part in path.parts):
            continue
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            raise CannotRun(f"cannot read {path}: {exc}") from exc
        example_ok = _is_test_path(relative)
        for line, iri, versioned_ok in _candidates(path, text):
            kind = judge(iri, names, example_ok=example_ok, versioned_ok=versioned_ok)
            if kind and not (kind == "versioned-namespace" and versioned_ok):
                findings.append(Finding(path.relative_to(root).as_posix(), line, kind, iri))
    return sorted(findings, key=lambda item: (item.path, item.line, item.iri))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, help="files (scan only those) or directories (scan all tracked)")
    parser.add_argument("--root", type=Path, help="repository or subtree to scan")
    parser.add_argument("--workspace", type=Path, help="workspace manifest naming every repository")
    args = parser.parse_args(argv)
    files = [path for path in args.roots if path.is_file()]
    dirs = ([args.root] if args.root else []) + [path for path in args.roots if not path.is_file()]
    findings: list[Finding] = []
    if files and not dirs:
        # Hook mode: pre-commit passes the changed files, so unrelated files never fail a change.
        base = Path.cwd().resolve()
        repository = repo_root(base)
        only = frozenset(path.resolve().relative_to(repository).as_posix() for path in files)
        dirs = [repository]
    else:
        only = None
    for root in dirs or [Path.cwd()]:
        names = set(CORE_PRODUCT_NAMES) | workspace_names(find_workspace(root.resolve(), args.workspace))
        names.add(repo_root(root.resolve()).name.lower())
        findings += scan(root, frozenset(names), only)
    if findings:
        print(f"FAIL: {len(findings)} ontology IRI(s) break the standard (base {BASE}<module>#):")
        for finding in findings[:80]:
            print("  " + finding.render())
        if len(findings) > 80:
            print(f"  ... and {len(findings) - 80} more")
        return 1
    print("OK: every custom ontology IRI is under the ontology base.")
    return 0
