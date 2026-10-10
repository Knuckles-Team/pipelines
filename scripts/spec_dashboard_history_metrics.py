"""Scope-aware transition accounting; existing landed records are baselines."""


def landed(item):
    return item['delivery_state'] in {'LANDED', 'VERIFIED', 'CLOSED'}


def totals(records, kind):
    items = [item for item in records.values() if item['kind'] == kind]
    done = sum(item['done'] for item in items)
    return {'total': len(items), 'done': done, 'remaining': len(items) - done,
            'unknown': sum(item['state'] == 'unknown' for item in items),
            'added': 0, 'removed': 0, 'landed': 0, 'completed': 0, 'reopened': 0}


def change_counts(previous, current, kind):
    before = {key: item for key, item in previous.items() if item['kind'] == kind}
    after = {key: item for key, item in current.items() if item['kind'] == kind}
    result = totals(current, kind)
    result['added'] = len(after.keys() - before.keys())
    result['removed'] = len(before.keys() - after.keys())
    for key in before.keys() & after.keys():
        old, new = before[key], after[key]
        result['landed'] += not landed(old) and landed(new)
        result['completed'] += not old['done'] and new['done']
        result['reopened'] += reopened(old, new)
    return result


def reopened(old, new):
    return (old['done'] and not new['done']) or (landed(old) and not landed(new))


def status(item):
    if item is None:
        return 'absent'
    return item['delivery_state'] + ' / ' + item['acceptance_state']


def events_at(previous, current, *, commit, date):
    events = []
    for key in sorted(previous.keys() | current.keys(), key=str):
        old, new = previous.get(key), current.get(key)
        if status(old) == status(new):
            continue
        item = new or old
        events.append({'commit': commit, 'observed_at': date, 'kind': item['kind'],
                       'id': item['id'], 'parent': item['parent'],
                       'before': status(old), 'after': status(new)})
    return events


def observations(snapshots):
    points, events = [], []
    previous = None
    for commit, date, records in snapshots:
        metrics = {kind: totals(records, kind) for kind in ('spec', 'requirement')}
        if previous is not None:
            metrics = {kind: change_counts(previous, records, kind) for kind in metrics}
            events.extend(events_at(previous, records, commit=commit, date=date))
        points.append({'commit': commit, 'observed_at': date, **metrics})
        previous = records
    return {'available': len(points) > 1,
            'reason': '' if len(points) > 1 else 'Only one or no commit snapshots available',
            'points': points, 'events': events,
            'baseline': ('States at the first snapshot have no known earlier changes. '
                         'A new record that is already landed adds scope. It is not an observed completion.')}
