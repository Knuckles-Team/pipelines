"""Bounded, offline first-parent observations of canonical status files."""
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
from fnmatch import fnmatchcase

if __package__:
    from .spec_dashboard_sources import source_records
    from .spec_dashboard_history_metrics import observations
else:
    from spec_dashboard_sources import source_records
    from spec_dashboard_history_metrics import observations


def git(root, *args, input=None):
    return subprocess.run(['git', '-C', str(root), *args], input=input,
                          capture_output=True, check=True, timeout=30, env=git_environment()).stdout


def git_environment():
    return {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}


def matches(parts, pattern):
    if not pattern:
        return not parts
    if pattern[0] == '**':
        return matches(parts, pattern[1:]) or bool(parts) and matches(parts[1:], pattern)
    return bool(parts) and fnmatchcase(parts[0], pattern[0]) and matches(parts[1:], pattern[1:])


def source_kind(path, config):
    if '_template' in path.parts:
        return None
    return next((source.get('kind', 'spec') for source in config['sources']
                 if matches(path.parts, Path(source['glob']).parts)), None)


def tree_entries(root, commit, config):
    entries = []
    for entry in git(root, 'ls-tree', '-r', '-z', commit).split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        path = Path(name.decode('utf-8'))
        kind = source_kind(path, config)
        if kind is not None:
            mode, object_type, oid = metadata.decode().split()
            if mode not in {'100644', '100755'} or object_type != 'blob':
                raise ValueError('Historical sources must be regular files')
            entries.append((oid, path, kind))
    return entries


def records_at(root, commit, config):
    entries = tree_entries(root, commit, config)
    stream = BytesIO(git(root, 'cat-file', '--batch', input=''.join(
        oid + '\n' for oid, _, _ in entries).encode()))
    result = {}
    for oid, path, kind in entries:
        header_oid, object_type, size = stream.readline().decode().split()
        if (header_oid, object_type) != (oid, 'blob'):
            raise ValueError('Invalid historical blob')
        raw = json.loads(stream.read(int(size)))
        stream.read(1)
        add_records(result, source_records(raw, path, kind))
    return result


def add_records(result, records):
    for item in records:
        key = (item['kind'], item['parent'], item['id'])
        if key in result:
            raise ValueError('Ambiguous historical record identity')
        result[key] = item


def history_snapshot(root, config, *, limit=100):
    try:
        return read_history(root, config, limit=limit)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        return {'available': False, 'reason': 'Canonical status history could not be verified',
                'points': [], 'events': []}


def read_history(root, config, *, limit):
    if not 2 <= limit <= 200:
        raise ValueError('History limit must be between 2 and 200')
    commits = git(root, 'log', '--first-parent', f'--max-count={limit+1}',
                  '--format=%H%x09%cI', 'HEAD').decode().splitlines()
    shallow = git(root, 'rev-parse', '--is-shallow-repository').strip() == b'true'
    selected = list(reversed(commits[:limit]))
    samples = [(line.split('\t')[0], line.split('\t')[1]) for line in selected]
    snapshots = [(commit, date, records_at(root, commit, config)) for commit, date in samples]
    result = observations(snapshots)
    result.update({'limit': limit, 'shallow': shallow, 'truncated': shallow or len(commits) > limit,
                   'sampled_commits': len(samples), 'basis': 'first-parent commit observations'})
    return result
