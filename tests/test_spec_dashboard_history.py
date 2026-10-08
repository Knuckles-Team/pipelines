"""Actual Git fixtures for bounded, changing-scope delivery observations."""
import json
import os
from pathlib import Path
import subprocess

from scripts.spec_dashboard_history import history_snapshot, matches
from scripts.spec_dashboard_charts import history_panels, daily_velocity

CONFIG = {'sources': [{'glob': 'specs/*/status.json', 'kind': 'spec'}]}


def initialize(root):
    root.mkdir()
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Fixture'], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.com'], check=True)
    return root


def commit(root, payload, day):
    path = root / 'specs' / 'sample' / 'status.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    if payload is None:
        path.unlink()
    else:
        path.write_text(json.dumps(payload))
    subprocess.run(['git', '-C', str(root), 'add', '--', 'specs/sample/status.json'], check=True)
    env = {**os.environ, 'GIT_AUTHOR_DATE': f'2026-01-{day:02}T12:00:00Z',
           'GIT_COMMITTER_DATE': f'2026-01-{day:02}T12:00:00Z'}
    subprocess.run(['git', '-C', str(root), 'commit', '-qm', f'observation {day}'], env=env, check=True)


def state(delivery, *, accepted=False, requirements=None):
    return {'spec_id': 'S', 'delivery_state': delivery,
            'acceptance_state': 'ACCEPTED' if accepted else 'NOT_AUDITED',
            'requirements': requirements or []}


def test_baseline_landed_is_not_new_completion(tmp_path):
    root = initialize(tmp_path / 'repo')
    commit(root, state('LANDED', accepted=True), 1)
    commit(root, state('LANDED', accepted=True, requirements=[{'id': 'R', 'delivery_state': 'LANDED'}]), 2)
    result = history_snapshot(root, CONFIG)
    assert result['available'] and not result['truncated']
    assert [point['spec']['landed'] for point in result['points']] == [0, 0]
    assert result['points'][-1]['requirement']['added'] == 1
    assert result['points'][-1]['requirement']['landed'] == 0
    assert result['points'][-1]['spec']['remaining'] == 0


def test_transitions_reopen_and_scope_removal(tmp_path):
    root = initialize(tmp_path / 'repo')
    commit(root, state('SPECIFIED'), 1)
    commit(root, state('LANDED', accepted=True), 2)
    commit(root, state('BUILDING'), 3)
    commit(root, None, 4)
    result = history_snapshot(root, CONFIG)
    points = result['points']
    assert [point['spec']['remaining'] for point in points] == [1, 0, 1, 0]
    assert [point['spec']['landed'] for point in points] == [0, 1, 0, 0]
    assert [point['spec']['completed'] for point in points] == [0, 1, 0, 0]
    assert points[2]['spec']['reopened'] == 1
    assert points[3]['spec']['removed'] == 1
    assert result['events'][-1]['after'] == 'absent'
    assert daily_velocity(points, 'spec') == [('2026-01-01', 0), ('2026-01-02', 1), ('2026-01-03', 0), ('2026-01-04', 0)]


def test_limit_excludes_old_transitions_and_keeps_unknown_baseline(tmp_path):
    root = initialize(tmp_path / 'repo')
    commit(root, state('SPECIFIED'), 1)
    commit(root, state('LANDED', accepted=True), 2)
    commit(root, state('CLOSED', accepted=True), 3)
    result = history_snapshot(root, CONFIG, limit=2)
    assert result['truncated'] and result['sampled_commits'] == 2
    assert sum(point['spec']['landed'] for point in result['points']) == 0
    assert sum(point['spec']['completed'] for point in result['points']) == 0


def test_shallow_and_single_snapshot_are_explicit(tmp_path):
    root = initialize(tmp_path / 'repo')
    commit(root, state('SPECIFIED'), 1)
    commit(root, state('LANDED'), 2)
    shallow = tmp_path / 'shallow'
    subprocess.run(['git', 'clone', '-q', '--depth=1', root.as_uri(), str(shallow)], check=True)
    result = history_snapshot(shallow, CONFIG)
    assert not result['available'] and result['shallow'] and result['truncated']
    assert result['sampled_commits'] == 1
    assert 'History unavailable' in history_panels(result, 'owner/repo')


def test_no_template_and_patterns_do_not_cross_segments():
    assert matches(('specs', 'a', 'status.json'), ('specs', '*', 'status.json'))
    assert not matches(('specs', 'a', 'nested', 'status.json'), ('specs', '*', 'status.json'))
    assert matches(('specs', 'a', 'nested', 'status.json'), ('specs', '**', 'status.json'))


def test_render_escapes_history_and_shows_scope(tmp_path):
    root = initialize(tmp_path / 'repo')
    commit(root, {**state('SPECIFIED'), 'spec_id': '<script>'}, 1)
    commit(root, {**state('LANDED'), 'spec_id': '<script>'}, 2)
    result = history_snapshot(root, CONFIG)
    page = history_panels(result, 'owner/repo')
    assert '<script>' not in page and '&lt;script&gt;' in page
    assert 'burndown' in page and 'velocity' in page
    assert 'Removed' in page and 'Reopened' in page
    assert 'not release or deployment dates' in page


def test_invalid_history_does_not_claim_empty_success(tmp_path):
    result = history_snapshot(tmp_path, CONFIG)
    assert result['available'] is False
    assert result['points'] == []
    assert 'could not be verified' in result['reason']
