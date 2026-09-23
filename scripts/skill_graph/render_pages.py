"""The three shared Pages projection files: index, concepts (level 1), components (level 2)."""

from __future__ import annotations

from typing import Any

from skill_graph.model import REPOS, VOCAB, repo_label
from skill_graph.render_shared import group_concepts_by_repo, render_concept_components


def render_concepts_md(corpus: dict[str, Any]) -> str:
    lines = [
        "# Concepts",
        "",
        "Level 1 of the skill graph: the top-level concepts each repo's own",
        "documentation nav or registry declares. Each concept links to its",
        "components (level 2, see [Components](components.md)).",
        "",
    ]
    by_repo = group_concepts_by_repo(corpus)
    for repo in sorted(by_repo):
        lines.append(f"## {repo_label(repo)}")
        lines.append("")
        for node in sorted(by_repo[repo], key=lambda n: n["label"]):
            count = len(node.get("hasComponent") or [])
            unit = "component" if count == 1 else "components"
            extra = f" ({count} {unit})" if count else ""
            lines.append(f"- **{node['label']}**{extra}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_components_md(corpus: dict[str, Any]) -> str:
    lines = [
        "# Components",
        "",
        "Level 2 of the skill graph: components under each concept, each",
        "documented by a man page (level 3) pointing at the exact source file",
        "that generated it. The full machine corpus, with every typed link,",
        "is published as [`corpus.jsonld`](corpus.jsonld).",
        "",
    ]
    nodes_by_id = {n["id"]: n for n in corpus["@graph"]}
    by_repo = group_concepts_by_repo(corpus)
    for repo in sorted(by_repo):
        lines.append(f"## {repo_label(repo)}")
        lines.append("")
        for concept in sorted(by_repo[repo], key=lambda n: n["label"]):
            lines.append(f"### {concept['label']}")
            lines.append("")
            render_concept_components(lines, nodes_by_id, concept)
    return "\n".join(lines).rstrip() + "\n"


def render_index_md(corpus: dict[str, Any]) -> str:
    concept_count = sum(1 for n in corpus["@graph"] if n["type"] == "Concept")
    component_count = sum(1 for n in corpus["@graph"] if n["type"] == "Component")
    manpage_count = sum(1 for n in corpus["@graph"] if n["type"] == "ManPage")
    return (
        "# Skill Graph\n\n"
        "One progressively disclosed corpus of the Knuckles agent ecosystem's "
        "concepts, components, and man pages, generated from each repo's own "
        "registries and documentation nav (RF-ADR-009 D1) — never hand-authored.\n\n"
        "- [Concepts](concepts.md) — level 1, "
        f"{concept_count} nodes across {len(REPOS)} repos.\n"
        "- [Components](components.md) — level 2, "
        f"{component_count} nodes, each documented by a man page.\n"
        f"- [`corpus.jsonld`](corpus.jsonld) — the full machine corpus "
        f"({manpage_count} man pages), consumable by agents directly over "
        "HTTP once this site is published; JSON-LD with `@id` IRIs under "
        f"`{VOCAB}`, the same namespace Epistemic Graph's own ontology uses.\n\n"
        "See [Ecosystem glossary](glossary.md) for the shared vocabulary this "
        "corpus's repo and concept names draw from.\n\n"
        "!!! note \"Not the same thing as `skills/skill-graphs`\"\n"
        "    `agent-utilities`' `docs/guides/skill-graph-migration.md` and the "
        "`skills/skill-graphs` repository name a **different** artifact: ~74 "
        "distilled third-party documentation knowledge-graphs (AWS, Django, "
        "Postgres, …) for Pydantic AI agents. This corpus is the RF-ADR-009 D1 "
        "documentation-architecture corpus for the ecosystem's own five core "
        "repos plus the two satellite UIs — unrelated data, coincidentally "
        "similar name.\n"
    )
