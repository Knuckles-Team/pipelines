"""Repository identities that survive the ecosystem's GitHub slug migration.

The package, import, ontology, and specification identities are deliberately
separate from GitHub repository slugs.  A caller may still report an old slug
while a newly renamed repository reports its new slug, so comparisons use the
canonical new slug without rewriting stable IDs or persisted references.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from urllib.parse import urlsplit

# Old repository slug -> canonical GitHub slug.  The keys are compatibility
# inputs only; stable ontology and specification prefixes remain unchanged.
REPOSITORY_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "epistemic-graph": "medulla",
        "agent-connector-sdk": "scion-sdk",
        "agent-utilities": "meristem",
        "agent-webui": "overstory",
        "agent-terminal-ui": "tuig",
        "geniusbot": "axil",
    }
)

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _parts(value: object) -> tuple[str, ...]:
    """Return namespace/slug parts from a Git URL, full ref, or bare slug."""
    text = str(value).strip()
    if not text:
        return ()
    if "://" in text:
        text = urlsplit(text).path
    elif text.startswith("git@") and ":" in text:
        text = text.split(":", 1)[1]
    text = text.rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    parts = tuple(part for part in text.split("/") if part)
    return parts if all(_SLUG_RE.fullmatch(part) for part in parts) else ()


def canonical_repository(value: object) -> str:
    """Canonicalize a repository slug while preserving a namespace when given."""
    parts = _parts(value)
    if not parts:
        return ""
    slug = REPOSITORY_ALIASES.get(parts[-1].casefold(), parts[-1])
    if len(parts) >= 2:
        return f"{parts[-2]}/{slug}"
    return slug


def repository_slug(value: object) -> str:
    """Return the canonical final repository slug from any supported ref."""
    canonical = canonical_repository(value)
    return canonical.rsplit("/", 1)[-1] if canonical else ""


def repository_matches(left: object, right: object) -> bool:
    """Compare repository refs with old/new aliases and case differences."""
    left_parts = canonical_repository(left).casefold().split("/")
    right_parts = canonical_repository(right).casefold().split("/")
    if not left_parts or not right_parts:
        return False
    if len(left_parts) == len(right_parts) == 2:
        return left_parts == right_parts
    return left_parts[-1] == right_parts[-1]
