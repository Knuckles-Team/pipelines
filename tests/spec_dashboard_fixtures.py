"""Isolated temporary Git repositories, including inside real Git hooks."""
import json
import subprocess
from pipelines_hooks.core.gitenv import sanitized_env


def run(root, *args, date=None):
    env = sanitized_env()
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(['git', '-C', str(root), *args], env=env, check=True)

def initialize(root):
    root.mkdir()
    run(root, 'init', '-q', '-b', 'main')
    run(root, 'config', 'user.name', 'Fixture')
    run(root, 'config', 'user.email', 'fixture@example.com')
    return root


def commit(root, payload, day):
    path = root / 'specs' / 'sample' / 'status.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    if payload is None:
        path.unlink()
    else:
        path.write_text(json.dumps(payload))
    run(root, 'add', '--', 'specs/sample/status.json')
    run(root, 'commit', '-qm', f'observation {day}', date=f'2026-01-{day:02}T12:00:00Z')


def state(delivery, *, accepted=False, requirements=None):
    return {'spec_id': 'S', 'delivery_state': delivery,
            'acceptance_state': 'ACCEPTED' if accepted else 'NOT_AUDITED',
            'requirements': requirements or []}
