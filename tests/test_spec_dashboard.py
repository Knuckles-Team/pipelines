"""Source semantics, escaping, and complete GitHub snapshot contracts."""
import io
import json
from pathlib import Path
from scripts.spec_dashboard import read_records, render, github_snapshot, record


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


def test_escape_and_empty_history():
    snapshot = {'repository': 'a/b', 'revision': 'abc', 'captured_at': 'now',
                'records': [], 'github': {'issues': {'available': False, 'error': '<fail>'}}}
    page = render(snapshot)
    assert 'No documented records' in page
    assert 'History is not available' in page
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
