"""Rendering helpers shared by the Pages projection and the per-repo man page."""

from __future__ import annotations

from typing import Any


def group_concepts_by_repo(corpus: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for node in corpus["@graph"]:
        if node["type"] != "Concept":
            continue
        repo = node.get("partOfRepo", "repo/unknown").split("/", 1)[-1]
        by_repo.setdefault(repo, []).append(node)
    return by_repo


def component_locator(nodes_by_id: dict[str, Any], comp: dict[str, Any]) -> str:
    man = nodes_by_id.get(comp.get("documentedBy", ""))
    source = man.get("sourcePath") if man else None
    anchor = man.get("anchor") if man else None
    if anchor:
        return f"`{source}#{anchor}`"
    if source:
        return f"`{source}`"
    return "_no source_"


def component_extra_bits(comp: dict[str, Any]) -> str:
    bits = []
    if comp.get("status"):
        bits.append(f"status: {comp['status']}")
    if comp.get("methodCount"):
        bits.append(f"{comp['methodCount']} methods")
    if comp.get("fileCount"):
        bits.append(f"{comp['fileCount']} files")
    return f" ({', '.join(bits)})" if bits else ""


def render_component_line(nodes_by_id: dict[str, Any], comp_id: str, with_extra: bool) -> str | None:
    comp = nodes_by_id.get(comp_id)
    if not comp:
        return None
    locator = component_locator(nodes_by_id, comp)
    extra = component_extra_bits(comp) if with_extra else ""
    return f"- **{comp['label']}**{extra} — {locator}"


def render_concept_components(
    lines: list[str],
    nodes_by_id: dict[str, Any],
    concept: dict[str, Any],
    *,
    with_extra: bool = False,
) -> None:
    comp_ids = concept.get("hasComponent") or []
    if not comp_ids:
        lines.append("_No components._")
        lines.append("")
        return
    for comp_id in comp_ids:
        line = render_component_line(nodes_by_id, comp_id, with_extra)
        if line:
            lines.append(line)
    lines.append("")
