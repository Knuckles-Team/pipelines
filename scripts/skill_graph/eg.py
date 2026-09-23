"""Registry-derived extraction for ``epistemic-graph``.

* ``architecture/component-registry.yml`` -- component identity, layer,
  capability_ids, status, concepts.
* ``contract/methods.json`` -- 429 generated-contract methods grouped by
  ``domain`` (one Component node per domain; the method id list is nested
  inside that node for machine consumers, not exploded into 429 nodes).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from skill_graph.model import Graph, slugify

_REPO = "repo/epistemic-graph"


def _add_component(graph: Graph, component: dict[str, Any]) -> str | None:
    component_id = component.get("component_id")
    if not component_id:
        return None
    man_id = f"manpage/epistemic-graph/component-registry/{slugify(component_id)}"
    graph.add(
        man_id,
        "ManPage",
        label=component_id,
        sourcePath="architecture/component-registry.yml",
        anchor=component_id,
        partOfRepo=_REPO,
    )
    comp_node_id = f"component/epistemic-graph/registry/{slugify(component_id)}"
    graph.add(
        comp_node_id,
        "Component",
        label=component_id,
        partOfRepo=_REPO,
        documentedBy=man_id,
        layer=component.get("layer"),
        status=component.get("status"),
        capabilityIds=component.get("capability_ids") or [],
        childComponent=[
            f"component/epistemic-graph/registry/{slugify(c)}"
            for c in (component.get("child_component_ids") or [])
        ],
        summary=(component.get("summary") or "").strip() or None,
    )
    return comp_node_id


def _add_registry_concepts(graph: Graph, concepts_to_components: dict[str, list[str]]) -> None:
    for concept_name, comp_ids in concepts_to_components.items():
        graph.add(
            f"concept/epistemic-graph/registry/{slugify(concept_name)}",
            "Concept",
            label=concept_name,
            partOfRepo=_REPO,
            hasComponent=sorted(comp_ids),
        )


def extract_registry(graph: Graph, repo_root: Path) -> None:
    registry_path = repo_root / "architecture" / "component-registry.yml"
    if not registry_path.is_file():
        return
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    concepts_to_components: dict[str, list[str]] = {}
    for component in data.get("components") or []:
        comp_node_id = _add_component(graph, component)
        if comp_node_id is None:
            continue
        for concept_name in component.get("concepts") or []:
            concepts_to_components.setdefault(concept_name, []).append(comp_node_id)
    _add_registry_concepts(graph, concepts_to_components)


def _group_methods_by_domain(methods: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_domain: dict[str, list[str]] = {}
    for method in methods:
        by_domain.setdefault(method.get("domain") or "unspecified", []).append(method.get("id"))
    return by_domain


def _add_contract_domain(graph: Graph, domain: str, method_ids: list[str]) -> str:
    man_id = f"manpage/epistemic-graph/contract-methods/{slugify(domain)}"
    graph.add(
        man_id,
        "ManPage",
        label=f"{domain} contract methods",
        sourcePath="contract/methods.json",
        anchor=domain,
        partOfRepo=_REPO,
    )
    comp_id = f"component/epistemic-graph/contract-domain/{slugify(domain)}"
    graph.add(
        comp_id,
        "Component",
        label=f"{domain} (contract domain)",
        partOfRepo=_REPO,
        documentedBy=man_id,
        methodCount=len(method_ids),
        methods=sorted(m for m in method_ids if m),
    )
    return comp_id


def extract_contract(graph: Graph, repo_root: Path) -> None:
    methods_path = repo_root / "contract" / "methods.json"
    if not methods_path.is_file():
        return
    data = json.loads(methods_path.read_text(encoding="utf-8"))
    by_domain = _group_methods_by_domain(data.get("methods") or [])
    component_ids = [
        _add_contract_domain(graph, domain, method_ids)
        for domain, method_ids in sorted(by_domain.items())
    ]
    graph.add(
        "concept/epistemic-graph/contract-methods",
        "Concept",
        label="Generated contract methods",
        partOfRepo=_REPO,
        hasComponent=sorted(component_ids),
        sourcePath="contract/methods.json",
        totalMethodCount=data.get("method_count"),
    )
