"""Assemble the full corpus and its four pipelines-root-relative Pages files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skill_graph import au, eg
from skill_graph.model import REPOS, SCHEMA, VOCAB, Graph
from skill_graph.nav import extract_nav
from skill_graph.render_pages import render_components_md, render_concepts_md, render_index_md

_CONTEXT = {
    "@vocab": VOCAB,
    "id": "@id",
    "type": "@type",
    "hasComponent": {"@type": "@id"},
    "hasConcept": {"@type": "@id"},
    "documentedBy": {"@type": "@id"},
    "childComponent": {"@type": "@id"},
    "partOfRepo": {"@type": "@id"},
}


def build_graph(workspace: Path) -> dict[str, Any]:
    graph = Graph()
    for slug, (dirname, url, name) in REPOS.items():
        graph.add(f"repo/{slug}", "Repository", label=name, pagesUrl=url)
        repo_root = workspace / dirname
        if not repo_root.is_dir():
            continue
        extract_nav(graph, slug, repo_root)
        if slug == "epistemic-graph":
            eg.extract_registry(graph, repo_root)
            eg.extract_contract(graph, repo_root)
        if slug == "agent-utilities":
            au.extract_pillars(graph, repo_root)
            au.extract_skills(graph, repo_root)
    ordered = [graph.nodes[k] for k in sorted(graph.nodes)]
    return {
        "@context": _CONTEXT,
        "schema": SCHEMA,
        "generatedBy": "pipelines/scripts/build_skill_graph.py",
        "@graph": ordered,
    }


def generate(workspace: Path) -> dict[str, str]:
    """The four pipelines-root-relative Pages projection files for ``build``/``check``."""
    corpus = build_graph(workspace)
    corpus_text = json.dumps(corpus, indent=2, sort_keys=False) + "\n"
    return {
        "pages/corpus.jsonld": corpus_text,
        "pages/concepts.md": render_concepts_md(corpus),
        "pages/components.md": render_components_md(corpus),
        "pages/index.md": render_index_md(corpus),
    }
