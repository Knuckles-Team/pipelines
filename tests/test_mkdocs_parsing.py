"""Shared readiness parsing rejects invalid declarations without executing tags."""

import pytest

from scripts.readiness.errors import ReadinessTckError
from scripts.readiness.mkdocs import mkdocs_docs_dir, mkdocs_site_url, validate_content_source


@pytest.mark.parametrize("text,reason", [
    ("docs_dir: docs\ndocs_dir: other\n", "mkdocs-duplicate-key"),
    ("site_name: one\nsite_name: two\n", "mkdocs-duplicate-key"),
    ("docs_dir: [\n", "mkdocs-yaml-invalid"),
    ("- docs\n", "mkdocs-mapping-required"),
])
def test_malformed_or_ambiguous_config_is_not_a_default(tmp_path, text, reason):
    (tmp_path / "docs").mkdir()
    (tmp_path / "mkdocs.yml").write_text(text)
    with pytest.raises(ReadinessTckError, match=reason):
        validate_content_source(tmp_path, "docs")


@pytest.mark.parametrize("text,expected", [
    ("", None),
    ("site_name: Fixture\n", None),
    ("docs_dir: docs\n", "docs"),
    ("docs_dir: &content docs\nextra: *content\n", "docs"),
    ("markdown_extensions:\n  - pymdownx.superfences:\n      custom_fences: !!python/name:example.inert\n", None),
])
def test_valid_missing_explicit_and_tagged_declarations(tmp_path, text, expected):
    (tmp_path / "mkdocs.yml").write_text(text)
    assert mkdocs_docs_dir(tmp_path) == expected


def test_site_url_rejects_duplicate_and_unreadable_config(tmp_path):
    path = tmp_path / "mkdocs.yml"
    path.write_text("site_url: https://example.com/\nsite_url: https://other.example/\n")
    with pytest.raises(ReadinessTckError, match="mkdocs-duplicate-key"):
        mkdocs_site_url(tmp_path)
    path.write_bytes(b"\xff")
    with pytest.raises(ReadinessTckError, match="mkdocs-unreadable"):
        mkdocs_docs_dir(tmp_path)
