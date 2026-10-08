"""Static HTML/SVG rendering for the spec delivery snapshot."""
from collections import Counter
import html
from urllib.parse import quote

if __package__:
    from .spec_dashboard_charts import history_panels
else:
    from spec_dashboard_charts import history_panels

def distribution(records, kind):
    return dict(Counter(item['state'] for item in records if item['kind'] == kind))


def bars(counts, title):
    escaped = html.escape(title)
    if not counts:
        return f'<h3>{escaped}</h3><p>No records documented.</p>'
    maximum = max(counts.values(), default=0) or 1
    rows = []
    for index, (label, count) in enumerate(sorted(counts.items())):
        y = 30 + index * 32
        rows.append(f'<text x="0" y="{y}">{html.escape(label)}: {count}</text>'
                    f'<rect x="180" y="{y-16}" width="{count/maximum*360}" height="20" fill="#4478cc"/>')
    return f'<h3>{escaped}</h3><svg role="img" aria-label="{escaped}" viewBox="0 0 560 {40+len(counts)*32}">{"".join(rows)}</svg>'


def safe_link(url, label):
    if not str(url).startswith('https://github.com/'):
        return html.escape(str(label))
    return f'<a href="{html.escape(str(url), quote=True)}">{html.escape(str(label))}</a>'


def inventory_rows(snapshot):
    rows = []
    repository = snapshot['repository']
    revision = snapshot['revision']
    for item in snapshot['records']:
        url = f'https://github.com/{repository}/blob/{revision}/{quote(item["source"])}'
        document_url = f'https://github.com/{repository}/blob/{revision}/{quote(item.get("document", item["source"]))}'
        cells = [safe_link(url, item['id']) + '<br>' + safe_link(document_url, item['title']), *[html.escape(str(item[key])) for key in
                 ('kind', 'parent', 'state', 'delivery_state', 'acceptance_state', 'release_state')]]
        rows.append('<tr>' + ''.join('<td>' + cell + '</td>' for cell in cells) + '</tr>')
    return ''.join(rows)


def github_sections(snapshot):
    sections = []
    for label, data in snapshot['github'].items():
        body = '<p>Unavailable: ' + html.escape(data.get('error', 'unknown failure')) + '</p>'
        if data['available']:
            body = '<p>' + str(len(data['items'])) + ' open at capture.</p><ul>'
            body += ''.join('<li>' + safe_link(item['html_url'], f'#{item["number"]} {item["title"]}')
                            + ' · updated ' + html.escape(item['updated_at']) + '</li>' for item in data['items'])
            body += '</ul>'
        sections.append('<h2>' + html.escape(label.replace('_', ' ').title()) + '</h2>' + body)
    return ''.join(sections)


def render(snapshot):
    repository = snapshot['repository']
    revision = snapshot['revision']
    charts = ''.join(bars(distribution(snapshot['records'], kind), kind.title() + ' status')
                     for kind in ('spec', 'requirement'))
    remaining = {kind: sum(not item['done'] for item in snapshot['records'] if item['kind'] == kind)
                 for kind in ('spec', 'requirement')}
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<title>Spec delivery dashboard</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#202938}'
            'table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:8px;border-bottom:1px solid #ccd}svg{max-width:560px;width:100%}'
            'a{color:#2357a1}section{overflow:auto}</style><h1>Spec delivery dashboard</h1><p>'
            + html.escape(repository) + ' · Captured ' + html.escape(snapshot['captured_at'])
            + '</p><p>Revision ' + html.escape(revision) + ' · <a href="snapshot.json">JSON snapshot</a></p>'
            '<p>Whole specs and requirement slices are counted separately. Done requires explicit LANDED/CLOSED and ACCEPTED. '
            'Source-landed does not imply released or deployed. Release evidence is unavailable in this v1 adapter.</p>'
            + charts + history_panels(snapshot.get('history', {}), repository)
            + '<h2>Current snapshot</h2><p>Remaining includes unknown and unaccepted records; deferred/rejected records remain visible.</p>'
            + bars(remaining, 'Records not explicitly done') + '<h2>Documented inventory</h2><section><table><thead><tr>'
            '<th>ID / source</th><th>Kind</th><th>Parent</th><th>State</th><th>Delivery</th><th>Acceptance</th><th>Release</th>'
            '</tr></thead><tbody>' + inventory_rows(snapshot) + '</tbody></table></section>' + github_sections(snapshot) + '</html>')
