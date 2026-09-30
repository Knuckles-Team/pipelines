"""MkDocs source and site declarations for the Pages readiness contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import ReadinessTckError, _fail
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
    Returns ``None`` for a missing file or an empty YAML document. Invalid
    YAML is a named error, never an absent declaration/default.
    """

    text = _mkdocs_text(root)
    if text is None:
        return None
    try:
        return yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        raise ReadinessTckError("mkdocs-yaml-invalid") from exc


def _mkdocs_text(root: Path) -> str | None:
    try:
        return (root / "mkdocs.yml").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as exc:
        raise ReadinessTckError("mkdocs-unreadable") from exc


def _top_level_mapping(document: yaml.Node) -> dict[str, yaml.Node]:
    """Keep tagged nodes inert and reject ambiguous top-level declarations."""
    if not isinstance(document, yaml.MappingNode):
        _fail("mkdocs-mapping-required")
    result = {}
    for key_node, value_node in document.value:
        if not isinstance(key_node, yaml.ScalarNode):
            _fail("mkdocs-key-invalid")
        if key_node.value in result:
            _fail("mkdocs-duplicate-key")
        result[key_node.value] = value_node
    return result


def _top_level_node(document: yaml.Node | None, key: str) -> yaml.Node | None:
    """Read one unambiguous top-level key; absence retains caller defaults."""
    if document is None:
        return None
    return _top_level_mapping(document).get(key)


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
