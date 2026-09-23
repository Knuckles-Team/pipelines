"""Nav-derived extraction: a repo's own ``mkdocs.yml`` ``nav:`` tree.

A top-level nav entry with children becomes a Concept, each child becomes a
Component, and the Markdown file it points at becomes a ManPage. A top-level
leaf (no children) is treated as both its own Concept and Component,
documented by that same file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from skill_graph.model import Graph, TolerantLoader, slugify


def load_mkdocs_nav(repo_root: Path) -> list[Any] | None:
    mkdocs_path = repo_root / "mkdocs.yml"
    if not mkdocs_path.is_file():
        return None
    data = yaml.load(mkdocs_path.read_text(encoding="utf-8"), Loader=TolerantLoader) or {}
    nav = data.get("nav")
    return nav if isinstance(nav, list) else None


@dataclass(frozen=True)
class _NavSink:
    """Where extracted nav nodes go: the graph, and which repo they belong to."""

    graph: Graph
    slug: str


def _extract_leaf(sink: _NavSink, label: str, target: str) -> None:
    man_id = f"manpage/{sink.slug}/nav/{slugify(target)}"
    sink.graph.add(man_id, "ManPage", label=label, sourcePath=target, partOfRepo=f"repo/{sink.slug}")
    comp_id = f"component/{sink.slug}/nav/{slugify(label)}"
    sink.graph.add(comp_id, "Component", label=label, partOfRepo=f"repo/{sink.slug}", documentedBy=man_id)
    sink.graph.add(
        f"concept/{sink.slug}/nav/{slugify(label)}",
        "Concept",
        label=label,
        partOfRepo=f"repo/{sink.slug}",
        hasComponent=[comp_id],
    )


def _extract_child(sink: _NavSink, parent_label: str, child: Any) -> str | None:
    if not isinstance(child, dict) or len(child) != 1:
        return None
    (child_label, child_target), = child.items()
    if not isinstance(child_target, str):
        return None  # a third nav level exists nowhere in scope today
    man_id = f"manpage/{sink.slug}/nav/{slugify(child_target)}"
    sink.graph.add(
        man_id, "ManPage", label=child_label, sourcePath=child_target, partOfRepo=f"repo/{sink.slug}"
    )
    comp_id = f"component/{sink.slug}/nav/{slugify(parent_label)}-{slugify(child_label)}"
    sink.graph.add(comp_id, "Component", label=child_label, partOfRepo=f"repo/{sink.slug}", documentedBy=man_id)
    return comp_id


def _extract_branch(sink: _NavSink, label: str, children: list[Any]) -> None:
    component_ids = [
        comp_id
        for child in children
        if (comp_id := _extract_child(sink, label, child)) is not None
    ]
    sink.graph.add(
        f"concept/{sink.slug}/nav/{slugify(label)}",
        "Concept",
        label=label,
        partOfRepo=f"repo/{sink.slug}",
        hasComponent=component_ids,
    )


def extract_nav(graph: Graph, slug: str, repo_root: Path) -> None:
    nav = load_mkdocs_nav(repo_root)
    if not nav:
        return
    sink = _NavSink(graph, slug)
    for entry in nav:
        if not isinstance(entry, dict) or len(entry) != 1:
            continue
        (label, target), = entry.items()
        if isinstance(target, str):
            _extract_leaf(sink, label, target)
        elif isinstance(target, list):
            _extract_branch(sink, label, target)
