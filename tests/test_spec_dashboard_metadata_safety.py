"""Adversarial labels, ambiguous ownership, and source-path boundaries."""
import pytest

from scripts.spec_dashboard_architecture import architecture_panel, mermaid
from scripts.spec_dashboard_metadata import enrich_records
from tests.test_spec_dashboard_metadata import fixture


def test_duplicate_ids_fail_before_ambiguous_edge_resolution(tmp_path):
    snapshot = fixture(tmp_path)
    snapshot['records'].append(dict(snapshot['records'][0]))
    with pytest.raises(ValueError, match='Duplicate spec or requirement ID'):
        enrich_records(tmp_path, snapshot)


def test_absolute_existing_and_planned_paths_remain_unmapped(tmp_path):
    actual = tmp_path / 'implementation.py'
    actual.write_text('pass')
    snapshot = fixture(tmp_path, f'Code: {actual} planned.py\n')
    enrich_records(tmp_path, snapshot)
    refs = snapshot['records'][0]['code_refs']
    assert all(not row['url'] for row in refs)
    assert {row['evidence'] for row in refs} == {'absolute source path rejected', 'missing source'}


def test_spec_labels_cannot_inject_html_svg_or_mermaid(tmp_path):
    snapshot = fixture(tmp_path)
    snapshot['records'][0]['id'] = 'X"/><script>alert(1)</script>'
    output = architecture_panel(snapshot)
    assert '<script>' not in output
    assert '&lt;script&gt;' in output
    assert '#spec-X%22%2F%3E%3Cscript%3E' in output
    assert '#34;' in mermaid(snapshot)


def test_source_url_escaping_and_unknown_external_targets(tmp_path):
    snapshot = fixture(tmp_path, 'Depends-on: [future](https://github.com/owner/unknown/blob/main/specs/new/spec.md)\nCode: [file](src/a%26b.py)\n')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/a&b.py').write_text('pass')
    enrich_records(tmp_path, snapshot)
    row = snapshot['records'][0]
    assert row['relations'][0]['evidence'] == 'external declaration; not verified'
    assert row['code_refs'][0]['url'].endswith('a%26b.py')
