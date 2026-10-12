"""Linked record inventory and GitHub snapshot sections for the delivery sheet."""
import html
from urllib.parse import quote


def safe_link(url, label):
    if not str(url).startswith('https://github.com/'):
        return html.escape(str(label))
    return f'<a href="{html.escape(str(url), quote=True)}">{html.escape(str(label))}</a>'


def blob_link(snapshot):
    base = f'https://github.com/{snapshot["repository"]}/blob/{snapshot["revision"]}/'

    def link(item, label, key='source'):
        return safe_link(base + quote(item.get(key, item['source'])), label)
    return link


def inventory_rows(snapshot):
    rows = []
    link = blob_link(snapshot)
    for item in snapshot['records']:
        cells = [link(item, item['id']) + '<br>' + link(item, item['title'], 'document') + definition_details(snapshot, item),
                 *[html.escape(str(item[key])) for key in
                   ('kind', 'parent', 'delivery_state')], evidence_links(snapshot, item)]
        rows.append('<tr id="req-' + quote(item['id'], safe='') + '">' + ''.join('<td>' + cell + '</td>' for cell in cells) + '</tr>')
    return ''.join(rows)


def inventory_panel(snapshot):
    count = len(snapshot['records'])
    return ('<p>Each status file gives one spec row. Each requirement gives one more row. '
            'A record without a valid state shows INVALID. Expand a Definition to read the canonical requirement and verification text.</p>'
            f'<details open><summary>All documented records <span class="mono">({count} rows)</span></summary>'
            '<div class="scroll"><table><thead><tr><th>ID / source</th><th>Kind</th><th>Parent</th><th>State</th><th>Commit / test evidence</th></tr></thead><tbody>'
            + inventory_rows(snapshot) + '</tbody></table></div></details>')


def github_sections(snapshot):
    sections = []
    for label, data in snapshot['github'].items():
        body = '<p>Not available: ' + html.escape(data.get('error', 'unknown failure')) + '</p>'
        if data['available']:
            body = '<p class="mono">' + str(len(data['items'])) + ' open at capture.</p><ul>'
            body += ''.join('<li>' + safe_link(item['html_url'], f'#{item["number"]} {item["title"]}')
                            + ' <span class="mono">updated ' + html.escape(item['updated_at']) + '</span></li>'
                            for item in data['items'])
            body += '</ul>'
        sections.append('<h3>' + html.escape(label.replace('_', ' ').title()) + '</h3>' + body)
    return ''.join(sections) + ('<div class="note"><p>The build reads GitHub one time. '
                                'This page makes no live API requests.</p></div>')


def evidence_links(snapshot, item):
    commits = [safe_link(f'https://github.com/{snapshot["repository"]}/commit/{sha}', sha) for sha in item.get('landed_in', [])]
    tests = []
    for test in item.get('verified_by', []):
        path = test.split('::')[0]
        if path.startswith('/') or '..' in path.split('/'):
            tests.append(html.escape(test))
        else:
            tests.append(safe_link(f'https://github.com/{snapshot["repository"]}/blob/{snapshot["revision"]}/' + quote(path), test))
    return '<br>'.join(commits + tests) or 'No recorded commit/test evidence'


def definition_details(snapshot, item):
    if item['kind'] != 'requirement':
        return ''
    context = str(item.get('parent') or 'Unknown spec') + ' / ' + item.get('parent_title', 'Unknown spec title')
    if 'definition' not in item:
        return '<p>' + html.escape(context) + ': definition unavailable in requirements.md.</p>'
    url = f'https://github.com/{snapshot["repository"]}/blob/{snapshot["revision"]}/' + quote(item['definition_source']) + '#L' + str(item['definition_line'])
    return ('<details><summary>Definition — ' + html.escape(context) + '</summary>'
            + safe_link(url, 'Canonical requirement and verification source')
            + '<div style="white-space:pre-wrap;overflow-wrap:anywhere">' + html.escape(item['definition']) + '</div></details>')
