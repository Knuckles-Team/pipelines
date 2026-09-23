"""Registry-derived extraction for ``agent-utilities``.

* ``docs/concepts.yaml`` -- 9 pillars over 1200+ concepts; only the pillar
  tier is surfaced as a Concept node (the full concept list stays in AU's own
  generated ``docs/concepts.yaml``, not duplicated here).
* ``deploy/release/prebundled-skills.catalog.json`` -- 13 prebundled skill
  bundles.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from skill_graph.model import Graph, slugify

_REPO = "repo/agent-utilities"


def extract_pillars(graph: Graph, repo_root: Path) -> None:
    concepts_path = repo_root / "docs" / "concepts.yaml"
    if not concepts_path.is_file():
        return
    data = yaml.safe_load(concepts_path.read_text(encoding="utf-8")) or {}
    counts: dict[str, int] = {}
    for concept in data.get("concepts") or []:
        pillar = concept.get("pillar")
        if pillar:
            counts[pillar] = counts.get(pillar, 0) + 1
    for pillar in data.get("pillars") or []:
        man_id = f"manpage/agent-utilities/concepts-yaml/{slugify(pillar)}"
        graph.add(
            man_id,
            "ManPage",
            label=f"{pillar} concepts",
            sourcePath="docs/concepts.yaml",
            anchor=pillar,
            partOfRepo=_REPO,
        )
        graph.add(
            f"concept/agent-utilities/pillar/{slugify(pillar)}",
            "Concept",
            label=pillar,
            partOfRepo=_REPO,
            documentedBy=man_id,
            conceptCount=counts.get(pillar, 0),
        )


def _add_skill(graph: Graph, entry: dict[str, Any]) -> str | None:
    name = entry.get("skill")
    if not name:
        return None
    man_id = f"manpage/agent-utilities/prebundled-skills/{slugify(name)}"
    graph.add(
        man_id,
        "ManPage",
        label=f"{name} (SKILL.md)",
        sourcePath="deploy/release/prebundled-skills.catalog.json",
        anchor=name,
        partOfRepo=_REPO,
    )
    comp_id = f"component/agent-utilities/skill/{slugify(name)}"
    graph.add(
        comp_id,
        "Component",
        label=name,
        partOfRepo=_REPO,
        documentedBy=man_id,
        fileCount=len(entry.get("files") or []),
    )
    return comp_id


def extract_skills(graph: Graph, repo_root: Path) -> None:
    catalog_path = repo_root / "deploy" / "release" / "prebundled-skills.catalog.json"
    if not catalog_path.is_file():
        return
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    component_ids = [
        comp_id
        for entry in (data.get("entries") or [])
        if (comp_id := _add_skill(graph, entry)) is not None
    ]
    graph.add(
        "concept/agent-utilities/prebundled-skills",
        "Concept",
        label="Prebundled skills",
        partOfRepo=_REPO,
        hasComponent=sorted(component_ids),
        sourcePath="deploy/release/prebundled-skills.catalog.json",
    )
