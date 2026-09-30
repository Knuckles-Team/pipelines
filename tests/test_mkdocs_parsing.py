"""Shared readiness parsing rejects invalid declarations without executing tags."""

import pytest

from scripts.readiness.errors import ReadinessTckError
from scripts.readiness.mkdocs import mkdocs_docs_dir, mkdocs_site_url, validate_content_source


@pytest.mark.parametrize("text,reason", [
    ("docs_dir: docs\ndocs_dir: other\n", "mkdocs-duplicate-key"),
    ("site_name: one\nsite_name: two\n", "mkdocs-duplicate-key"),
    ("docs_dir: [\n", "mkdocs-yaml-invalid"),
    ("- docs\n", "mkdocs-mapping-required"),
    ("!custom {}\n", "mkdocs-mapping-required"),
    ("<<: {docs_dir: other}\n", "mkdocs-merge-key"),
    ('"<<": {docs_dir: other}\n', "mkdocs-merge-key"),
    ("<<: [{docs_dir: other}, {docs_dir: docs}]\n", "mkdocs-merge-key"),
    ("docs_dir: docs\ndocs_dir: docs\n<<: {}\n", "mkdocs-duplicate-key"),
    ("? [docs_dir]\n: docs\n", "mkdocs-key-invalid"),
    ("!custom docs_dir: docs\n", "mkdocs-key-invalid"),
    ("true: docs\n", "mkdocs-key-invalid"),
    ("docs_dir: !custom docs\n", "content-source-docs-dir-invalid"),
    ("docs_dir: null\n", "content-source-docs-dir-invalid"),
    ("docs_dir: *undefined\n", "mkdocs-yaml-invalid"),
    ("docs_dir: docs\n---\nsite_name: two\n", "mkdocs-yaml-invalid"),
    ("key: &key docs_dir\n*key: docs\ndocs_dir: other\n", "mkdocs-duplicate-key"),
])
def test_malformed_or_ambiguous_config_is_not_a_default(tmp_path, text, reason):
    (tmp_path / "docs").mkdir()
    (tmp_path / "mkdocs.yml").write_text(text)
    with pytest.raises(ReadinessTckError, match=reason):
        validate_content_source(tmp_path, "docs")


@pytest.mark.parametrize("text,expected", [
    ("", None),
    ("site_name: Fixture\n", None),
    ("extra: {nested: {<<: {docs_dir: other}}, docs_dir: other}\n", None),
    ("extra: &self {child: *self}\n", None),
    ("extra: {docs_dir: one, docs_dir: two}\ndocs_dir: docs\n", "docs"),
    ("value: &content docs\ndocs_dir: *content\n", "docs"),
    ("key: &key docs_dir\n*key: docs\n", "docs"),
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


def test_absent_file_retains_default(tmp_path):
    assert mkdocs_docs_dir(tmp_path) is None


@pytest.mark.parametrize("text", ["site_url: !custom https://example.com/\n", "site_url: 123\n"])
def test_site_url_requires_string_authority(tmp_path, text):
    (tmp_path / "mkdocs.yml").write_text(text)
    with pytest.raises(ReadinessTckError, match="site-url-invalid"):
        mkdocs_site_url(tmp_path)
