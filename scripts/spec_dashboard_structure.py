"""Panel A tree: repository, specs with requirement counts, and records not done."""
import html
from collections import Counter

EMPTY = '<li><small>No documented records.</small></li>'


def spec_leaves(records, limit):
    specs = [item for item in records if item['kind'] == 'spec']
    per_spec = Counter(item['parent'] for item in records if item['kind'] == 'requirement')
    leaves = [f'<li><span class="mono">{html.escape(item["id"])}</span><span class="mono">{per_spec[item["id"]]}</span></li>'
              for item in specs[:limit]]
    if len(specs) > limit:
        leaves.append(f'<li><small>{len(specs) - limit} more specs. Panel D shows all specs.</small></li>')
    return len(specs), ''.join(leaves) or EMPTY


def tally(records, kind, *, open_only=False):
    return sum(item['kind'] == kind and not (open_only and item['done']) for item in records)


def not_done_leaves(records):
    rows = [('Requirements', 'all slices in all specs', tally(records, 'requirement')),
            ('Requirements not done', 'unknown and unaccepted included', tally(records, 'requirement', open_only=True)),
            ('Specs not done', 'whole specs only', tally(records, 'spec', open_only=True))]
    return ''.join(f'<li><span>{label}<small>{note}</small></span><span class="mono">{value}</span></li>'
                   for label, note, value in rows)


def structure_panel(snapshot, limit=14):
    total, leaves = spec_leaves(snapshot['records'], limit)
    return (f'<div class="root"><b>{html.escape(snapshot["repository"])}</b><span>Spec delivery</span></div>'
            f'<div class="stem"></div><div class="branches"><div><div class="node">Specs '
            f'<span class="mono">({total})</span></div><ul class="leaves">{leaves}</ul></div>'
            '<div><div class="node">Records not done</div><ul class="leaves">'
            + not_done_leaves(snapshot['records']) + '</ul></div></div>'
            '<div class="note"><p>Each spec shows its requirement count. Panel J lists every record.</p></div>')
