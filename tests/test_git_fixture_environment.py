"""A hook's parent index and objects remain untouched by temporary Git fixtures."""
import subprocess

from tests.git_fixture_environment import fixture_git_environment


def git(root, *arguments, index=None):
    return subprocess.check_output(['git', '-C', str(root), *arguments], env=fixture_git_environment(index=index))


def test_child_git_preserves_parent_index_under_hook_routing(tmp_path, monkeypatch):
    parent, child = tmp_path / 'parent', tmp_path / 'child'
    parent.mkdir()
    child.mkdir()
    git(parent, 'init', '-q')
    (parent / 'kept.txt').write_text('parent staged work')
    git(parent, 'add', 'kept.txt')
    index = parent / '.git/index'
    before = index.read_bytes()
    monkeypatch.setenv('GIT_DIR', str(parent / '.git'))
    monkeypatch.setenv('GIT_WORK_TREE', str(parent))
    monkeypatch.setenv('GIT_INDEX_FILE', str(index))
    git(child, 'init', '-q')
    (child / 'fixture.txt').write_text('child work')
    git(child, 'add', 'fixture.txt')
    assert git(child, 'ls-files') == b'fixture.txt\n'
    assert git(parent, 'ls-files') == b'kept.txt\n'
    assert index.read_bytes() == before


def test_explicit_fixture_index_and_nonrouting_options_survive(tmp_path, monkeypatch):
    monkeypatch.setenv('GIT_DIR', 'caller-routing')
    monkeypatch.setenv('GIT_AUTHOR_NAME', 'Fixture Author')
    alternate = tmp_path / 'alternate.index'
    environment = fixture_git_environment(index=alternate)
    assert 'GIT_DIR' not in environment
    assert environment['GIT_INDEX_FILE'] == str(alternate)
    assert environment['GIT_AUTHOR_NAME'] == 'Fixture Author'
