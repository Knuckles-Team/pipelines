"""Snapshot extras for the spec-delivery page: spec edges and concept ids (PIPE-PAGES-R012, R013)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spec_dashboard_concepts import row_concepts
from spec_dashboard_relations import extends_edges, spec_edges
from spec_graph_load import load_repo


def spec_texts(root):
    return {
        p.parent.name: p.read_text(encoding="utf-8")
        for p in sorted(Path(root).glob("specs/*/spec.md"))
    }


def snapshot_edges(root):
    """Depends-on and extends edges as plain lists, ready for the snapshot JSON."""
    try:
        requirements = list(load_repo(Path(root)).values())
    except (OSError, ValueError):
        requirements = []
    edges = spec_edges(requirements) + extends_edges(spec_texts(root))
    return [list(edge) for edge in sorted(set(edges))]


def snapshot_concepts(root, records):
    """Map spec id to its concept ids (explicit `Concepts:` line or markers in code roots)."""
    texts = spec_texts(root)
    return {
        r["id"]: row_concepts(texts.get(r["id"], ""), [], [root])
        for r in records
        if r["kind"] == "spec"
    }
