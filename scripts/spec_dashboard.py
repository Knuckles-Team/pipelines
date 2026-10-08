#!/usr/bin/env python3
"""Dependency-free, source-backed spec delivery snapshot (contract v1)."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

if __package__:
    from .spec_dashboard_render import render
    from .spec_dashboard_sources import read_records, record
    from .spec_dashboard_history import history_snapshot, git
else:
    from spec_dashboard_render import render
    from spec_dashboard_sources import read_records, record
    from spec_dashboard_history import history_snapshot, git


def github_snapshot(repository, token, opener=urlopen):
    """A failed page invalidates the complete collection, never a fake empty list."""
    result = {}
    for label, endpoint in [('issues', 'issues'), ('pull_requests', 'pulls')]:
        try:
            result[label] = {'available': True, 'items': fetch_pages(repository, endpoint, token, opener=opener)}
        except Exception as error:
            result[label] = {'available': False, 'items': None,
                             'error': type(error).__name__ + ': GitHub snapshot unavailable'}
    return result


def fetch_pages(repository, endpoint, token, *, opener):
    items = []
    for page in range(1, 10001):
        url = f'https://api.github.com/repos/{repository}/{endpoint}?state=open&per_page=100&page={page}'
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'spec-delivery-dashboard'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        with opener(Request(url, headers=headers), timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError('Invalid GitHub response')
        items.extend(public_items(batch, endpoint))
        if len(batch) < 100:
            return items
    raise ValueError('Pagination bound exceeded')


def public_items(batch, endpoint):
    for item in batch:
        if endpoint == 'issues' and 'pull_request' in item:
            continue
        yield {key: item[key] for key in ('number', 'title', 'html_url', 'created_at', 'updated_at')}


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--config', type=Path, default=Path('.config/spec-dashboard.json'))
    parser.add_argument('--output', type=Path, default=Path('site/spec-delivery'))
    parser.add_argument('--repository', required=True)
    parser.add_argument('--history-limit', type=int, choices=range(2, 201), default=100)
    return parser


def parse_options(argv):
    parser = argument_parser()
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        parser.error('repository must be owner/name')
    root = args.root.resolve()
    config = json.loads((root / args.config).read_text())
    if config.get('version') != 1:
        parser.error('config version must be 1')
    for source in config['sources']:
        if Path(source['glob']).is_absolute() or '..' in Path(source['glob']).parts:
            parser.error('source globs must stay within root')
    return args, root, config


def create_snapshot(args, root, config):
    revision = git(root, 'rev-parse', 'HEAD').decode().strip()
    snapshot = {'version': 1, 'repository': args.repository, 'revision': revision,
                'captured_at': datetime.now(timezone.utc).isoformat(),
                'records': read_records(root, config),
                'history': history_snapshot(root, config, limit=args.history_limit),
                'github': github_snapshot(args.repository, os.environ.get('GITHUB_TOKEN'))}
    return snapshot


def main(argv=None):
    args, root, config = parse_options(argv)
    snapshot = create_snapshot(args, root, config)
    output = root / args.output
    output.mkdir(parents=True, exist_ok=True)
    (output / 'snapshot.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    (output / 'index.html').write_text(render(snapshot))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
