"""Delivery source links stay distinct from dependency and verification evidence."""
import json
from copy import deepcopy

from scripts.spec_dashboard_architecture import architecture_panel, mermaid, relationships_panel
from scripts.spec_dashboard_metadata import enrich_records
from scripts.spec_dashboard_sources import read_records


def fixture(root, text='', plan=''):
    for slug, identifier in [('first', 'AU-CONTROL'), ('second', 'AU-OTHER')]:
        directory = root / 'specs' / slug
        directory.mkdir(parents=True)
        (directory / 'spec.md').write_text('# ' + identifier + '\n' + (text if slug == 'first' else ''))
        (directory / 'plan.md').write_text(plan if slug == 'first' else '')
        (directory / 'status.json').write_text(json.dumps({'spec_id': identifier, 'delivery_state': 'SPECIFIED', 'requirement_ids': [identifier + '-R001']}))
    records = read_records(root, {'sources': [{'glob': 'specs/*/status.json'}]})
    return {'repository': 'Knuckles-Team/demo', 'revision': 'a' * 40, 'records': records}


def test_local_and_external_dependencies_have_links_and_canonical_identity(tmp_path):
    remote = 'https://github.com/Knuckles-Team/graph-os/blob/main/specs/host/spec.md'
    snapshot = fixture(tmp_path, 'Depends-on: AU-OTHER-R001, [host](' + remote + ')\n')
    enrich_records(tmp_path, snapshot)
    first = snapshot['records'][0]
    assert first['id'] == 'AU-CONTROL'
    assert {edge['kind'] for edge in first['relations']} == {'depends on'}
    assert {edge['repository'] for edge in first['relations']} == {'Knuckles-Team/demo', 'Knuckles-Team/graph-os'}
    page = relationships_panel(snapshot)
    assert 'specs/second/spec.md' in page and remote in page
    assert 'not verified' in page
    assert 'depends on' in mermaid(snapshot)


def test_mentions_and_shared_code_never_become_dependencies(tmp_path):
    snapshot = fixture(tmp_path, 'Unblocks AU-OTHER-R001. See [other](../second/spec.md).\nCode: src/entry.py\n')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/entry.py').write_text('pass\n')
    enrich_records(tmp_path, snapshot)
    first = snapshot['records'][0]
    assert [edge['kind'] for edge in first['relations']] == ['references']
    assert first['code_refs'][0]['role'] == 'implementation'
    assert 'depends on' not in mermaid(snapshot)


def test_implementation_tests_docs_and_missing_sources_are_distinct(tmp_path):
    snapshot = fixture(tmp_path, 'Code: src/main.py:12 tests/test_main.py docs/guide.md missing.py\n')
    for file in ['src/main.py', 'tests/test_main.py', 'docs/guide.md']:
        path = tmp_path / file
        path.parent.mkdir()
        path.write_text('example')
    enrich_records(tmp_path, snapshot)
    refs = snapshot['records'][0]['code_refs']
    assert {row['role'] for row in refs} == {'implementation', 'test', 'documentation'}
    assert any(row['url'].endswith('src/main.py#L12') for row in refs)
    assert next(row for row in refs if row['label'] == 'missing.py')['url'] == ''
    assert all('verified' in row['evidence'] or row['evidence'] == 'missing source' for row in refs)


def test_unknowns_empty_and_isolated_specs_remain_discoverable(tmp_path):
    snapshot = fixture(tmp_path, 'Depends-on: MISSING\n')
    enrich_records(tmp_path, snapshot)
    assert snapshot['records'][0]['relations'][0]['url'] == ''
    assert 'Unassigned' in architecture_panel(snapshot)
    for number in range(45):
        snapshot['records'].append({'id': f'ORPHAN-{number}', 'kind': 'spec', 'source': 's.json'})
    assert all(f'ORPHAN-{number}' in architecture_panel(snapshot) for number in range(45))
    assert 'dependencies unknown' in relationships_panel(snapshot)
    assert 'Architecture is unknown' in architecture_panel({'records': []})


def test_deterministic_escaped_output_and_plan_diagram_coverage(tmp_path):
    snapshot = fixture(tmp_path, 'Component: runtime "]; evil <script>\n', '```mermaid\nflowchart LR\n  A-->B\n```\n')
    enrich_records(tmp_path, snapshot)
    original = deepcopy(snapshot)
    output = mermaid(snapshot)
    snapshot['records'].reverse()
    assert output == mermaid(snapshot)
    assert '<script>' not in architecture_panel(snapshot)
    assert '#34;' in output and '#60;script#62;' in output
    assert 'source plan diagrams' in architecture_panel(snapshot)
    assert 'no plan diagram declared' in architecture_panel(snapshot)
    assert original['records'][0]['plan_diagrams'] == ['flowchart LR\n  A-->B\n']


def test_examples_unsafe_links_and_parent_escape_are_not_mappings(tmp_path):
    snapshot = fixture(tmp_path, '```\nDepends-on: AU-OTHER\n```\nCode: [bad](javascript:alert) [escape](../../../../etc/passwd)\n')
    enrich_records(tmp_path, snapshot)
    first = snapshot['records'][0]
    assert not first['relations']
    assert not any(row['url'] for row in first['code_refs'])
    assert 'javascript:' not in relationships_panel(snapshot)


def test_enrichment_preserves_delivery_records_and_status_bytes(tmp_path):
    snapshot = fixture(tmp_path, 'Component: runtime\n')
    previous = deepcopy(snapshot['records'])
    files = {path: path.read_bytes() for path in tmp_path.glob('specs/*/status.json')}
    snapshot['history'] = {'points': [{'date': '2020-01-01', 'remaining': 7}]}
    enrich_records(tmp_path, snapshot)
    for before, after in zip(previous, snapshot['records']):
        assert all(after[key] == value for key, value in before.items())
    assert all(path.read_bytes() == content for path, content in files.items())
    assert snapshot['history']['points'][0]['remaining'] == 7


def test_code_cells_replace_concepts(tmp_path):
    from scripts.spec_dashboard_panels import specs_panel
    from scripts.spec_dashboard_render import count_caption

    snapshot = fixture(tmp_path)
    enrich_records(tmp_path, snapshot)
    output = specs_panel(snapshot, lambda row, label: label)
    assert '<th>Code references</th>' in output and 'Concepts' not in output
    assert 'Not mapped' in output
    assert '2 with no code mapped' in count_caption(snapshot)


def test_generator_entry_point_writes_architecture(tmp_path, monkeypatch):
    from scripts import spec_dashboard as dashboard

    fixture(tmp_path, 'Component: gateway\nDepends-on: AU-OTHER\n')
    config = tmp_path / '.config/spec-dashboard.json'
    config.parent.mkdir()
    config.write_text('{"version":1,"sources":[{"glob":"specs/*/status.json"}]}')
    monkeypatch.setattr(dashboard, 'git', lambda *args: b'a' * 40)
    monkeypatch.setattr(dashboard, 'github_snapshot', lambda *args: {})
    assert dashboard.main(['--root', str(tmp_path), '--repository', 'Knuckles-Team/connector']) == 0
    generated = tmp_path / 'site/spec-delivery'
    assert 'Spec architecture' in (generated / 'index.html').read_text()
    assert '-->|depends on|' in (generated / 'architecture.mmd').read_text()
    assert json.loads((generated / 'snapshot.json').read_text())['records'][0]['component'] == 'gateway'


def test_commit_and_bound_test_evidence_survive_normalization(tmp_path):
    from scripts.spec_dashboard_records import inventory_panel
    from scripts.spec_dashboard_sources import record
    from pathlib import Path

    row = record({'id': 'R1', 'landed_in': ['a' * 12, '<bad>'], 'verified_by': ['tests/test_run.py::test_run']}, Path('specs/a/status.json'), 'requirement')
    assert row['landed_in'] == ['a' * 12]
    snapshot = {'repository': 'Knuckles-Team/demo', 'revision': 'b' * 40, 'records': [row]}
    output = inventory_panel(snapshot)
    assert '/commit/' + 'a' * 12 in output
    assert '/tests/test_run.py' in output
    assert 'tests/test_run.py::test_run' in output
    assert 'code_refs' not in row
