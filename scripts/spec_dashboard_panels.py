"""Sheet panels for the current snapshot: structure, states, definitions and specs."""
import html
from collections import Counter

if __package__:
    from .spec_dashboard_style import mark
else:
    from spec_dashboard_style import mark

ORDER = ['unknown', 'documented', 'planned', 'in-progress', 'built', 'source-landed', 'closed', 'done',
         'deferred', 'rejected']
DEFINITIONS = [
    ('UNKNOWN', 'unknown', 'The status file has no valid delivery state.'),
    ('SPECIFIED', 'documented', 'A spec describes the work. The build is not started.'),
    ('PLANNED', 'planned', 'The work has a plan. The build is not started.'),
    ('BUILDING', 'in-progress', 'The work is in progress on a branch.'),
    ('BUILT', 'built', 'The code is complete but it is not on main.'),
    ('LANDED', 'source-landed', 'The code is on the main branch.'),
    ('CLOSED', 'closed', 'The record is closed. It counts as landed.'),
    ('DEFERRED', 'deferred', 'The work moves to a later time.'),
    ('REJECTED', 'rejected', 'The team does not do this work.'),
]
LANDED = {'LANDED', 'CLOSED'}
DELIVERY = {state: name for name, state, _ in DEFINITIONS} | {'done': 'ACCEPTED'}
STEPS = [base * 10 ** power for power in range(9) for base in (1, 2, 5)]


def distribution(records, kind):
    return dict(Counter(item['state'] for item in records if item['kind'] == kind))


def ticks(total):
    """Nice tick values from 0 up to the scale end; the end value is always shown."""
    step = next(size for size in STEPS if total / size <= 5)
    return [value for value in range(0, total, step) if value == 0 or total - value >= step / 2] + [total]


def tick_scale(total):
    cells = []
    for value in ticks(total):
        css = ' class="end"' if value == total and value else ''
        cells.append(f'<span{css} style="left:{value / total * 100:.2f}%">{value}</span>')
    return '<div class="ticks" aria-hidden="true">' + ''.join(cells) + '</div>'


def limit_bar(label, *, detail, count, total):
    return (f'<div class="limit"><div class="head"><b>{html.escape(label)}</b>'
            f'<span>{count} of {total} {html.escape(detail)}</span></div>'
            f'<div class="track" role="img" aria-label="{html.escape(label)}: {count} of {total}">'
            f'<i style="width:{count / total * 100:.2f}%"></i></div>' + tick_scale(total) + '</div>')


def state_bars(records, kind, noun):
    counts = distribution(records, kind)
    heading = f'<h3>{html.escape(noun.title())} <span class="mono">({sum(counts.values())})</span></h3>'
    if not counts:
        return heading + '<p>No documented records.</p>'
    total = sum(counts.values())
    rows = [limit_bar(f'{DELIVERY.get(state, state.upper())} ({state})', detail=noun, count=counts[state], total=total)
            for state in sorted(counts, key=lambda state: ORDER.index(state) if state in ORDER else len(ORDER))]
    return heading + ''.join(rows)


def states_panel(records):
    return (state_bars(records, 'requirement', 'requirements') + state_bars(records, 'spec', 'specs')
            + '<div class="note"><p>Each bar shows one state against all records of the same kind.</p>'
            '<p>Remaining work includes unknown and unaccepted records. Deferred and rejected records stay visible.</p></div>')


def definitions_panel():
    rows = [f'<tr><td class="mono">{name}</td><td>{html.escape(text)}</td><td>{mark(name in LANDED, "Landed" if name in LANDED else "Not landed")}</td></tr>'
            for name, _, text in DEFINITIONS]
    rows.append('<tr><td class="mono">ACCEPTED</td><td>The record is LANDED or CLOSED, and an audit accepts it.</td>'
                f'<td>{mark(True, "Done")}</td></tr>')
    return ('<div class="scroll"><table><thead><tr><th>delivery_state</th><th>Definition</th><th>Status</th></tr></thead>'
            '<tbody>' + ''.join(rows) + '</tbody></table></div><div class="note">'
            '<p>Specs and requirements have separate counts. A spec never takes the state of its requirements.</p>'
            '<p>Done needs LANDED or CLOSED, and ACCEPTED. Landed does not mean released or deployed.</p></div>')


def spec_row(spec, children, link):
    landed = sum(item['delivery_state'] in LANDED for item in children)
    done = sum(item['done'] for item in children)
    state = mark(True, spec['delivery_state']) if spec['done'] else html.escape(spec['delivery_state'])
    return (f'<tr><td><span class="mono">{link(spec, spec["id"])}</span><small>{html.escape(spec["title"])}</small></td>'
            f'<td class="n">{len(children)}</td><td class="n">{landed}/{len(children)}</td>'
            f'<td class="n">{done}</td><td class="mono">{state}</td></tr>')


def spec_rows(snapshot, link):
    children = {}
    for item in snapshot['records']:
        if item['kind'] == 'requirement':
            children.setdefault(item['parent'], []).append(item)
    return [spec_row(spec, children.get(spec['id'], []), link)
            for spec in snapshot['records'] if spec['kind'] == 'spec']


def specs_panel(snapshot, link):
    rows = spec_rows(snapshot, link)
    if not rows:
        return '<p>No documented records.</p>'
    return ('<div class="scroll"><table class="specs"><thead><tr><th>Spec / title</th><th class="n">Req.</th>'
            '<th class="n">Landed</th><th class="n">Done</th><th>Spec state</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></div><div class="note"><p>Landed counts LANDED and CLOSED requirements.'
            ' Done counts accepted requirements only.</p><p>The spec state comes from the spec status file only.</p></div>')
