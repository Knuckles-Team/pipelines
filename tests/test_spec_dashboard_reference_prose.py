"""Real SDK reference prose must not manufacture relationship targets."""
import pytest

from scripts.spec_dashboard_architecture import mermaid, relationships_panel
from scripts.spec_dashboard_metadata import enrich_records
from tests.test_spec_dashboard_metadata import fixture


@pytest.mark.spec("PIPE-PAGES-R013.2")
def test_sdk_reference_prose_is_unparsed_evidence_not_word_edges(tmp_path):
    prose = 'this contract derives from connector context and MCP progress needs.'
    snapshot = fixture(tmp_path, plan='References: ' + prose + '\n')
    enrich_records(tmp_path, snapshot)
    row = snapshot['records'][0]
    assert row['relations'] == []
    assert row['unparsed_references'] == [{'text': prose, 'declared_in': 'specs/first/plan.md'}]
    assert 'Unparsed reference declaration: ' + prose in relationships_panel(snapshot)
    assert '|references|' not in mermaid(snapshot)


def test_valid_unresolved_identifiers_links_and_paths_survive(tmp_path):
    value = 'SDK-EXTERNAL-R001.2 [other](../second/spec.md) docs/guide.md explanation'
    snapshot = fixture(tmp_path, 'References: ' + value + '\n')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/guide.md').write_text('Guide')
    enrich_records(tmp_path, snapshot)
    row = snapshot['records'][0]
    assert {edge['label'] for edge in row['relations']} == {'SDK-EXTERNAL-R001.2', 'other', 'docs/guide.md'}
    unknown = next(edge for edge in row['relations'] if edge['label'] == 'SDK-EXTERNAL-R001.2')
    assert unknown['url'] == '' and unknown['kind'] == 'references'
    assert '|references|' in mermaid(snapshot)
    assert row['unparsed_references'][0]['text'] == value


def test_unparsed_reference_evidence_is_escaped(tmp_path):
    snapshot = fixture(tmp_path, 'References: <script>alert(1)</script> MCP\n')
    enrich_records(tmp_path, snapshot)
    page = relationships_panel(snapshot)
    assert '<script>' not in page
    assert '&lt;script&gt;' in page
    assert snapshot['records'][0]['relations'] == []


@pytest.mark.parametrize(('target', 'relative_file', 'fragment'), [
    ('templates/mkdocs-theme/base.mkdocs.yml', 'templates/mkdocs-theme/base.mkdocs.yml', ''),
    ('.pre-commit-config.yaml', '.pre-commit-config.yaml', ''),
    ('src/module.test.ts', 'src/module.test.ts', ''),
    ('../other/spec.md#requirements', 'specs/other/spec.md', '#requirements'),
    ('.gitignore', '.gitignore', ''),
])
def test_reference_paths_preserve_dots_dotfiles_and_fragments(tmp_path, target, relative_file, fragment):
    snapshot = fixture(tmp_path, 'References: ' + target + '\n')
    path = tmp_path / relative_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('Source')
    enrich_records(tmp_path, snapshot)
    row = snapshot['records'][0]
    assert row['unparsed_references'] == []
    assert row['relations'][0]['url'] == 'https://github.com/Knuckles-Team/demo/blob/' + 'a' * 40 + '/' + relative_file + fragment


@pytest.mark.parametrize('target', [
    'MCP', 'needs.', '.', '/etc/config.yaml', r'C:\temp\file.md',
    '%2e%2e/file.md', 'file.md#<script>', 'javascript:alert(1)',
])
def test_reference_path_recognition_excludes_prose_and_unsafe_syntax(tmp_path, target):
    snapshot = fixture(tmp_path, 'References: ' + target + '\n')
    enrich_records(tmp_path, snapshot)
    assert snapshot['records'][0]['relations'] == []
    assert snapshot['records'][0]['unparsed_references'][0]['text'] == target


def test_reference_file_shape_does_not_bypass_checkout_containment(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + '-outside.md')
    outside.write_text('Outside checkout')
    target = '../../../' + outside.name + '#requirements'
    snapshot = fixture(tmp_path, 'References: ' + target + '\n')
    enrich_records(tmp_path, snapshot)
    edge = snapshot['records'][0]['relations'][0]
    assert edge['url'] == ''
    assert edge['evidence'] == 'missing source'
