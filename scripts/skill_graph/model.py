"""Shared corpus primitives: the node store, repo registry, and slug/YAML helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

VOCAB = "http://knuckles.team/kg#"
SCHEMA = "knuckles-skill-graph/v1"

# slug -> (repo directory relative to --workspace, Pages URL, display name)
REPOS: dict[str, tuple[str, str, str]] = {
    "medulla": (
        "medulla",
        "https://knuckles-team.github.io/medulla/",
        "Medulla",
    ),
    "meristem": (
        "meristem",
        "https://knuckles-team.github.io/meristem/",
        "Meristem",
    ),
    "scion-sdk": (
        "scion-sdk",
        "https://knuckles-team.github.io/scion-sdk/",
        "Scion SDK",
    ),
    "arbora": ("arbora", "https://knuckles-team.github.io/arbora/", "Arbora"),
    "overstory": (
        "overstory",
        "https://knuckles-team.github.io/overstory/",
        "Overstory",
    ),
    "tuig": (
        "tuig",
        "https://knuckles-team.github.io/tuig/",
        "Tuig",
    ),
    "axil": ("axil", "https://knuckles-team.github.io/axil/", "Axil"),
}


def repo_label(slug: str) -> str:
    return REPOS.get(slug, (slug, "", slug))[2]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class TolerantLoader(yaml.SafeLoader):
    """A SafeLoader that ignores unrecognized tags instead of raising.

    Only the ``nav:`` key is read from a repo's ``mkdocs.yml``; several repos'
    ``markdown_extensions:`` blocks use mkdocs-material's
    ``!!python/name:...`` tags for emoji extensions, which plain
    ``yaml.safe_load`` cannot construct. Mapping every unknown tag to its raw
    scalar/sequence/mapping value keeps those keys (never read here) inert
    instead of failing the whole parse.
    """


def _ignore_unknown(loader: yaml.SafeLoader, _tag_suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


TolerantLoader.add_multi_constructor("tag:yaml.org,2002:python/", _ignore_unknown)


@dataclass
class Graph:
    """A typed-node store, keyed by ``@id``; later ``add`` calls merge fields."""

    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(self, node_id: str, node_type: str, **fields: Any) -> str:
        node = {"id": node_id, "type": node_type}
        node.update({k: v for k, v in fields.items() if v not in (None, [], "")})
        existing = self.nodes.get(node_id)
        if existing is not None:
            existing.update(node)
        else:
            self.nodes[node_id] = node
        return node_id
