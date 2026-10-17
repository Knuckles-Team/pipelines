"""Concept references for spec-delivery rows (PIPE-PAGES-R012)."""

from __future__ import annotations

import html
import re
from pathlib import Path

MARKER = re.compile(r"CONCEPT:([A-Za-z0-9_.-]+)")
EXPLICIT = re.compile(r"^\s*Concepts:\s*(.+)$", re.MULTILINE)
SKIP = {".git", "node_modules", ".venv", "__pycache__"}


def _scan(path: Path) -> set[str]:
    try:
        return set(MARKER.findall(path.read_text(errors="ignore")))
    except OSError:
        return set()


def _files(target: Path) -> list[Path]:
    """The scannable files at or under one code root."""
    paths = [target] if target.is_file() else target.rglob("*")
    return [path for path in paths if path.is_file() and not SKIP & set(path.parts)]


def concepts_for_row(row_roots, roots) -> list[str]:
    """Sorted CONCEPT:<ID> markers found under the code roots a row names."""
    found: set[str] = set()
    for base in roots:
        for root in row_roots:
            for path in _files(Path(base) / root):
                found |= _scan(path)
    return sorted(found)


def explicit_concepts(text) -> list[str]:
    """Identifiers from a `Concepts: A, B` line; empty when absent."""
    match = EXPLICIT.search(text or "")
    if not match:
        return []
    return sorted({i.strip() for i in match.group(1).split(",") if i.strip()})


def row_concepts(text, row_roots, roots) -> list[str]:
    """The explicit list wins over derived markers."""
    return explicit_concepts(text) or concepts_for_row(row_roots, roots)


def concept_slug(ident: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", ident.lower()).strip("-")


def concept_links(ids, base) -> str:
    if not ids:
        return '<span class="no-concept">no concept mapped</span>'
    return " ".join(
        f'<a href="{html.escape(base)}concepts/#concept-{concept_slug(i)}">{html.escape(i)}</a>' for i in ids
    )


def unmapped_count(rows) -> int:
    return sum(1 for ids in rows if not ids)


def check_concept_links(page, concepts_md):
    """Concept anchors the page links to but concepts.md does not define."""
    wanted = set(re.findall(r"concepts/#(concept-[a-z0-9-]+)", page))
    defined = set(re.findall(r'id="(concept-[a-z0-9-]+)"', concepts_md))
    return sorted(wanted - defined)
