"""First-parent merge attribution and untrusted historical shape fixtures."""
import os
import subprocess
from test_spec_dashboard_history import initialize, commit, state, CONFIG
from scripts.spec_dashboard_history import history_snapshot


def test_merge_is_observed_on_first_parent_not_branch_author_date(tmp_path):
    root = initialize(tmp_path / 'repo')
    commit(root, state('SPECIFIED'), 1)
    subprocess.run(['git', '-C', str(root), 'checkout', '-qb', 'delivery'], check=True)
    commit(root, state('LANDED'), 2)
    subprocess.run(['git', '-C', str(root), 'checkout', '-q', 'main'], check=True)
    env = {**os.environ, 'GIT_AUTHOR_DATE': '2026-01-03T12:00:00Z', 'GIT_COMMITTER_DATE': '2026-01-03T12:00:00Z'}
    subprocess.run(['git', '-C', str(root), 'merge', '--no-ff', '-qm', 'land delivery', 'delivery'], env=env, check=True)
    result = history_snapshot(root, CONFIG)
    assert result['sampled_commits'] == 2
    assert result['points'][-1]['observed_at'].startswith('2026-01-03')
    assert result['points'][-1]['spec']['landed'] == 1


def test_malformed_old_status_is_unavailable_not_fake_zero_history(tmp_path):
    root = initialize(tmp_path / 'repo')
    commit(root, [], 1)
    commit(root, state('LANDED'), 2)
    result = history_snapshot(root, CONFIG)
    assert result['available'] is False
    assert result['points'] == []
    assert result['reason'] == 'Canonical status history could not be verified'
