"""First-parent merge attribution and untrusted historical shape fixtures."""
from spec_dashboard_fixtures import initialize, commit, state, run
from test_spec_dashboard_history import CONFIG
from scripts.spec_dashboard_history import history_snapshot


def test_merge_is_observed_on_first_parent_not_branch_author_date(tmp_path):
    root = initialize(tmp_path / 'repo')
    commit(root, state('SPECIFIED'), 1)
    run(root, 'checkout', '-qb', 'delivery')
    commit(root, state('LANDED'), 2)
    run(root, 'checkout', '-q', 'main')
    run(root, 'merge', '--no-ff', '-qm', 'land delivery', 'delivery', date='2026-01-03T12:00:00Z')
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


def test_inherited_git_directory_cannot_redirect_source_or_fixture(tmp_path, monkeypatch):
    other = initialize(tmp_path / 'other')
    commit(other, state('LANDED', accepted=True), 1)
    monkeypatch.setenv('GIT_DIR', str(other / '.git'))
    monkeypatch.setenv('GIT_WORK_TREE', str(other))
    monkeypatch.setenv('GIT_INDEX_FILE', str(other / '.git' / 'index'))
    root = initialize(tmp_path / 'source')
    commit(root, state('SPECIFIED'), 1)
    commit(root, state('BUILDING'), 2)
    result = history_snapshot(root, CONFIG)
    assert result['available'] and result['sampled_commits'] == 2
    assert result['points'][-1]['spec']['remaining'] == 1
    assert result['points'][-1]['spec']['done'] == 0
    assert history_snapshot(other, CONFIG)['sampled_commits'] == 1
