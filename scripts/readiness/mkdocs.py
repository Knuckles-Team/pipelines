"""MkDocs source and site declarations for the Pages readiness contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import _fail
from .filesystem import _safe_existing_dir, _safe_root


def _mkdocs_document(root: Path) -> yaml.Node | None:
    """Compose ``root/mkdocs.yml`` into a node tree without constructing
    anything.

    `yaml.compose` runs only the parser/composer stage (it calls
    `Loader.get_single_node`, never `get_single_data`), so it never constructs
    a Python object for any node. A scalar value is read as a
    `ScalarNode.value` string, and a Python-specific tag elsewhere in the
    document stays an inert node carrying that tag string. Nothing importable,
    callable, or constructible is produced from untrusted YAML.
    Returns ``None`` for a missing/unreadable file or one that fails to parse.
    """

    try:
        text = (root / "mkdocs.yml").read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        return None


def _top_level_node(document: yaml.Node | None, key: str) -> yaml.Node | None:
    """Return the mapping's declared top-level ``key`` value node, if any."""

    if not isinstance(document, yaml.MappingNode):
        return None
    for key_node, value_node in document.value:
        if isinstance(key_node, yaml.ScalarNode) and key_node.value == key:
            return value_node
    return None


def _docs_dir_node(document: yaml.Node | None) -> yaml.Node | None:
    """Return the mapping's declared ``docs_dir`` value node, if any."""

    return _top_level_node(document, "docs_dir")


def mkdocs_site_url(root: Path) -> str:
    """Return the repository's declared ``site_url``."""

    node = _top_level_node(_mkdocs_document(root), "site_url")
    if node is None:
        _fail("site-url-required")
    if not isinstance(node, yaml.ScalarNode) or not node.value.strip():
        _fail("site-url-invalid")
    return node.value


def mkdocs_docs_dir(root: Path) -> str | None:
    """Return the repository's declared ``docs_dir``, or ``None`` if absent."""

    node = _docs_dir_node(_mkdocs_document(root))
    if node is None:
        return None
    if not isinstance(node, yaml.ScalarNode) or not node.value.strip():
        _fail("content-source-docs-dir-invalid")
    return node.value


def validate_content_source(root: str | Path, content_source: str) -> dict[str, Any]:
    """Validate a declared ``content_source`` before it is trusted."""

    if not isinstance(content_source, str) or not content_source.strip():
        _fail("content-source-required")
    workspace = _safe_root(root)
    _safe_existing_dir(workspace, content_source, "content-source")
    declared = mkdocs_docs_dir(workspace)
    if declared is not None and declared != content_source:
        _fail("content-source-mismatch")
    return {"ok": True, "content_source": content_source, "mkdocs_docs_dir": declared}
