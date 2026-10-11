"""Sheet panels for the current snapshot: structure, states, definitions and specs."""
import html
from collections import Counter

if __package__:
    from .spec_dashboard_concepts import concept_links
    from .spec_dashboard_style import mark
else:
    from spec_dashboard_concepts import concept_links
    from spec_dashboard_style import mark

ORDER = ['specified', 'landed', 'verified', 'invalid']
DEFINITIONS = [
    ('SPECIFIED', 'specified', 'The requirement is written. No code for it is on the default branch.'),
    ('LANDED', 'landed', 'A commit that carries its ID in a Spec trailer is on the default branch.'),
    ('VERIFIED', 'verified', 'It is LANDED and a test bound to its ID exists.'),
]
LANDED = {'LANDED', 'VERIFIED'}
DELIVERY = {state: name for name, state, _ in DEFINITIONS} | {'invalid': 'INVALID'}
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
            '<p>Percentages count current rows. Done means VERIFIED.</p></div>')


def definitions_panel(records=()):
    rows = [f'<tr><td class="mono">{name}</td><td>{html.escape(text)}</td></tr>' for name, _, text in DEFINITIONS]
    return ('<div class="scroll"><table class="legend"><thead><tr><th>State</th><th>Definition</th></tr></thead>'
            '<tbody>' + ''.join(rows) + '</tbody></table></div><div class="note">'
            '<p>A spec state is the lowest state of its rows. Done means VERIFIED.</p>'
            f'<p>Invalid state: <b class="mono" id="invalid-count">{sum(item['state'] == 'invalid' for item in records)}</b></p></div>')


def spec_row(spec, children, link, *, repo=''):
    landed = sum(item['delivery_state'] in LANDED for item in children)
    done = sum(item['done'] for item in children)
    state = mark(True, spec['delivery_state']) if spec['done'] else html.escape(spec['delivery_state'])
    base = f'https://knuckles-team.github.io/{repo}/' if repo else './'
    cell = concept_links(spec.get('concepts', []), base)
    return (f'<tr id="spec-{html.escape(spec["id"])}"><td><span class="mono">{link(spec, spec["id"])}</span><small>{html.escape(spec["title"])}</small></td>'
            f'<td class="n">{len(children)}</td><td class="n">{landed}/{len(children)}</td>'
            f'<td class="n">{done}</td><td class="mono">{state}</td><td>{cell}</td></tr>')


def spec_rows(snapshot, link):
    children = {}
    for item in snapshot['records']:
        if item['kind'] == 'requirement':
            children.setdefault(item['parent'], []).append(item)
    return [spec_row(spec, children.get(spec['id'], []), link, repo=snapshot['repository'].split('/')[-1])
            for spec in snapshot['records'] if spec['kind'] == 'spec']


def specs_panel(snapshot, link):
    rows = spec_rows(snapshot, link)
    if not rows:
        return '<p>No documented records.</p>'
    return ('<div class="scroll"><table class="specs"><thead><tr><th>Spec / title</th><th class="n">Req.</th>'
            '<th class="n">Landed</th><th class="n">Done</th><th>Spec state</th><th>Concepts</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></div><div class="note"><p>Landed counts LANDED and VERIFIED requirements.'
            ' Done counts VERIFIED requirements only.</p><p>The spec state comes from the spec status file only.</p></div>')
