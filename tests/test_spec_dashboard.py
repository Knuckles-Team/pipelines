"""Source semantics, escaping, and complete GitHub snapshot contracts."""
import io
import json
from pathlib import Path

import pytest

from scripts.spec_dashboard import github_snapshot, read_records, record, render


def test_canonical_nested_status_and_template(tmp_path):
    for name in ('live', '_template'):
        path = tmp_path / 'specs' / name
        path.mkdir(parents=True)
        (path / 'status.json').write_text(json.dumps({'spec_id': 'S', 'delivery_state': 'SPECIFIED',
            'requirement_ids': ['R1', 'R2'], 'requirements': [{'id': 'R1', 'delivery_state': 'LANDED',
            'evidence': [{'description': 'PRIVATE'}]}]}))
    records = read_records(tmp_path, {'sources': [{'glob': 'specs/*/status.json'}]})
    assert len(records) == 3
    assert records[0]['state'] == 'documented'
    assert records[1]['state'] == 'source-landed'
    assert records[2]['state'] == 'unknown'
    assert not any(item['done'] for item in records)
    assert 'PRIVATE' not in json.dumps(records)


def test_completion_requires_explicit_acceptance():
    assert record({'delivery_state': 'CLOSED'}, Path('x/status.json'), 'spec')['done'] is False
    assert record({'delivery_state': 'LANDED', 'acceptance_state': 'ACCEPTED'},
                  Path('x/status.json'), 'spec')['done'] is True
    assert record({'delivery_state': 'invented'}, Path('x/status.json'), 'spec')['state'] == 'unknown'


def test_generated_lifecycle_states_are_recognised():
    verified = record({'delivery_state': 'VERIFIED'}, Path('x/status.json'), 'requirement')
    retired = record({'delivery_state': 'RETIRED'}, Path('x/status.json'), 'requirement')
    landed = record({'delivery_state': 'LANDED'}, Path('x/status.json'), 'requirement')
    assert (verified['state'], verified['done']) == ('verified', True)
    assert (retired['state'], retired['done']) == ('retired', True)
    assert (landed['state'], landed['done']) == ('source-landed', False)


def test_escape_and_empty_records():
    snapshot = {'repository': 'a/b', 'revision': 'abc', 'captured_at': 'now',
                'records': [], 'github': {'issues': {'available': False, 'error': '<fail>'}}}
    page = render(snapshot)
    assert 'No documented records' in page
    assert '&lt;fail&gt;' in page and '<fail>' not in page
    snapshot['records'] = [record({'id': '<script>'}, Path('x/status.json'), 'spec')]
    assert '<script>' not in render(snapshot)


def test_paginated_issue_pr_separation_and_allowlist():
    calls = []
    item = {'number': 1, 'title': 'title', 'html_url': 'https://github.com/a/b/issues/1',
            'created_at': 'now', 'updated_at': 'now', 'body': 'PRIVATE'}
    def opener(request, timeout):
        calls.append(request.full_url)
        batch = [dict(item, pull_request={})] * 100 if request.full_url.endswith('&page=1') else [item]
        return io.BytesIO(json.dumps(batch).encode())
    result = github_snapshot('a/b', None, opener)
    assert len(calls) == 4
    assert len(result['issues']['items']) == 1
    assert len(result['pull_requests']['items']) == 101
    assert 'PRIVATE' not in json.dumps(result)


def test_late_page_failure_is_unavailable_not_partial():
    def opener(request, timeout):
        raise OSError('token secret must not leak')
    result = github_snapshot('a/b', None, opener)
    assert result['issues']['items'] is None
    assert result['pull_requests']['available'] is False
    assert 'secret' not in json.dumps(result)


def test_successful_empty_collections_render():
    snapshot = {'repository': 'a/b', 'revision': 'abc', 'captured_at': 'now',
                'records': [], 'github': {'issues': {'available': True, 'items': []}}}
    assert '0 open at capture.' in render(snapshot)


def test_external_document_symlink_cannot_publish_heading(tmp_path):
    root = tmp_path / 'repo'
    source = root / 'specs' / 'live'
    source.mkdir(parents=True)
    (source / 'status.json').write_text('{"spec_id":"SAFE","delivery_state":"SPECIFIED"}')
    outside = tmp_path / 'private.md'
    outside.write_text('# PRIVATE OUTSIDE HEADING\n')
    document = source / 'spec.md'
    document.symlink_to(outside)
    config = {'sources': [{'glob': 'specs/*/status.json'}]}
    records = read_records(root, config)
    assert records[0]['title'] == 'SAFE'
    assert 'document' not in records[0]
    assert 'PRIVATE' not in json.dumps(records)
    document.unlink()
    document.write_text('# Public spec heading\n')
    records = read_records(root, config)
    assert records[0]['title'] == 'Public spec heading'
    assert records[0]['document'] == 'specs/live/spec.md'


def _page_for(tmp_path, ids):
    root = tmp_path
    for spec_id in ids:
        path = root / 'specs' / spec_id.lower()
        path.mkdir(parents=True, exist_ok=True)
        (path / 'status.json').write_text(json.dumps({'spec_id': spec_id, 'delivery_state': 'SPECIFIED'}))
    return {'repository': 'a/b', 'revision': 'abc', 'captured_at': 'now',
            'records': read_records(root, {'sources': [{'glob': 'specs/*/status.json'}]}), 'github': {}}


@pytest.mark.spec("PIPE-PAGES-R016.1")
def test_snapshot_has_no_history_field(tmp_path):
    from scripts import spec_dashboard
    assert not hasattr(spec_dashboard, 'history_snapshot')
    assert not any('history' in action.dest for action in spec_dashboard.argument_parser()._actions)


@pytest.mark.spec("PIPE-PAGES-R016.2")
def test_page_has_no_history_panels(tmp_path):
    page = render(_page_for(tmp_path, ['KEEP-1'])).lower()
    for marker in ('observed delivery history', 'timeline', 'observed changes', 'burndown', 'velocity'):
        assert marker not in page


@pytest.mark.spec("PIPE-PAGES-R016.3")
def test_removed_id_absent_from_page(tmp_path):
    import subprocess
    run = lambda *a: subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=T', '-c', 'user.email=t@e.invalid', *a], check=True, capture_output=True)
    run('init', '-q')
    _page_for(tmp_path, ['GONE-1', 'KEEP-1'])
    run('add', '--', 'specs')
    run('commit', '-q', '-m', 'both')
    run('rm', '-q', '-r', '--', 'specs/gone-1')
    run('commit', '-q', '-m', 'drop')
    page = render(_page_for(tmp_path, ['KEEP-1']))
    assert 'KEEP-1' in page and 'GONE-1' not in page


@pytest.mark.spec("PIPE-PAGES-R016.4")
def test_workflow_does_not_reference_history_scripts():
    text = (Path(__file__).parents[1] / '.github/workflows/pages_pipeline.yml').read_text()
    assert 'spec_dashboard_history' not in text and 'spec_dashboard_charts' not in text
