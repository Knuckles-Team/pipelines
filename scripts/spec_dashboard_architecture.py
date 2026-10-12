"""Grouped component diagrams and a lossless relationship index, without browser scripts."""
import html
from collections import defaultdict
from urllib.parse import quote

if __package__:
    from .spec_dashboard_records import safe_link
else:
    from spec_dashboard_records import safe_link


def code_links(refs):
    if not refs:
        return 'Not mapped'
    return '<br>'.join(safe_link(row['url'], row['label']) + ' <small>' + html.escape(row.get('role', 'implementation') + ': ' + row['evidence']) + '</small>' for row in refs)


def groups(snapshot):
    grouped = defaultdict(list)
    for row in snapshot['records']:
        if row['kind'] == 'spec':
            grouped[(snapshot['repository'], row.get('component', 'Unassigned'))].append(row)
    return [(key, sorted(rows, key=lambda row: row['id'])) for key, rows in sorted(grouped.items())]


def package_diagram(label, rows):
    """UML package containment: every spec remains linked, including isolated specs."""
    height = 58 + 36 * len(rows)
    parts = [f'<svg viewBox="0 0 680 {height}" role="img" aria-label="{html.escape(label, quote=True)}" style="width:100%;max-width:680px">',
             '<rect x="1" y="1" width="678" height="32" fill="none" stroke="currentColor"/>',
             f'<text x="12" y="23" fill="currentColor">{html.escape(label)}</text>',
             f'<rect x="1" y="33" width="678" height="{height - 34}" fill="none" stroke="currentColor"/>']
    for index, row in enumerate(rows):
        y = 44 + index * 36
        parts.append(f'<a href="#spec-{quote(row["id"], safe="")}"><rect x="12" y="{y}" width="656" height="28" fill="none" stroke="currentColor"/><text x="22" y="{y + 20}" fill="currentColor">{html.escape(row["id"])}</text></a>')
    return ''.join(parts) + '</svg>'


def architecture_panel(snapshot):
    sections = ['<p>Packages group specs by repository and declared component. Unassigned means no component was declared. '
                'Code links do not prove coverage. <a href="architecture.mmd">Mermaid source</a>.</p>']
    for (repo, component), rows in groups(snapshot):
        title = f'{repo} / {component} ({len(rows)})'
        diagrams = ''.join(package_diagram(title, rows[start:start + 20]) for start in range(0, len(rows), 20))
        plans = ''.join(plan_diagrams(row) for row in rows)
        sections.append(f'<details open><summary>{html.escape(title)}</summary>{diagrams}{plans}</details>')
    return ''.join(sections) if groups(snapshot) else '<p>No documented specs. Architecture is unknown.</p>'


def relationships_panel(snapshot):
    sections = ['<p>Depends on means a declared prerequisite. Extends and references do not imply prerequisite order. '
                'Shared code never creates dependencies. External targets are source declarations, not verified delivery.</p>']
    for (repo, component), rows in groups(snapshot):
        cells = []
        for row in rows:
            source = f'<a href="#spec-{quote(row["id"], safe="")}">{html.escape(row["id"])}</a>'
            relations = row.get('relations', [])
            if not relations:
                cells.append(f'<tr><td>{source}</td><td colspan="3">No relationships declared; dependencies unknown</td></tr>')
            for edge in relations:
                cells.append(f'<tr><td>{source}</td><td>{html.escape(edge["kind"])}</td><td>{safe_link(edge["url"], edge["label"])}</td><td>{html.escape(edge["repository"] + ": " + edge["evidence"] + "; source: " + edge.get("declared_in", "unknown"))}</td></tr>')
        sections.append(f'<details open><summary>{html.escape(repo + " / " + component)}</summary><div class="scroll"><table><thead><tr><th>Spec</th><th>Relationship</th><th>Target</th><th>Evidence</th></tr></thead><tbody>{"".join(cells)}</tbody></table></div></details>')
    return ''.join(sections)


def mermaid_label(value):
    """Mermaid numeric entities keep source text from becoming diagram syntax."""
    return ''.join(character if character.isascii() and (character.isalnum() or character in ' /._-') else f'#{ord(character)};' for character in value)


def mermaid(snapshot):
    lines = ['flowchart LR']
    ids = {}
    for group_index, ((repo, component), rows) in enumerate(groups(snapshot)):
        lines.append(f'  subgraph g{group_index}["{mermaid_label(repo + " / " + component)}"]')
        for row in rows:
            node = f'n{len(ids)}'
            ids[row['id']] = node
            lines.append(f'    {node}["{mermaid_label(row["id"])}"]')
        lines.append('  end')
    return '\n'.join(lines + mermaid_edges(snapshot, ids)) + '\n'


def mermaid_edges(snapshot, ids):
    lines, external = [], {}
    for _, rows in groups(snapshot):
        for row in rows:
            for edge in row.get('relations', []):
                target = mermaid_target(snapshot, edge, ids=ids, external=external, lines=lines)
                arrow = '-->' if edge['kind'] == 'depends on' else '-.->'
                lines.append(f'  {ids[row["id"]]} {arrow}|{edge["kind"]}| {target}')
    return lines


def plan_diagrams(row):
    diagrams = row.get('plan_diagrams', [])
    if not diagrams:
        return '<p>' + html.escape(row['id']) + ': no plan diagram declared.</p>'
    return '<details><summary>' + html.escape(row['id']) + ': source plan diagrams (Mermaid)</summary>' + ''.join('<pre><code>' + html.escape(diagram) + '</code></pre>' for diagram in diagrams) + '</details>'


def mermaid_target(snapshot, edge, *, ids, external, lines):
    key = edge['url'] or edge['label']
    # Only this repository's exact source URL resolves a local node.
    local = next((other['id'] for other in snapshot['records'] if other['kind'] == 'spec' and edge['url'] == f'https://github.com/{snapshot["repository"]}/blob/{snapshot["revision"]}/' + quote(other.get('document', other['source']))), None)
    if not local and key not in external:
        external[key] = f'e{len(external)}'
        label = edge['repository'] + ' / ' + edge['label']
        lines.append(f'  {external[key]}["{mermaid_label(label)}"]')
    return ids[local] if local else external[key]
