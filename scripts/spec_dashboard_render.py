"""Static HTML/SVG rendering for the spec delivery snapshot, laid out as one drawing sheet."""
import html
from pathlib import PurePosixPath

if __package__:
    from .spec_dashboard_charts import history_caption, history_charts
    from .spec_dashboard_history_views import history_tables, history_timeline
    from .spec_dashboard_records import blob_link, github_sections, inventory_panel, safe_link
    from .spec_dashboard_panels import definitions_panel, distribution, specs_panel, states_panel
    from .spec_dashboard_structure import structure_panel
    from .spec_dashboard_style import STYLE, panel, zones
else:
    from spec_dashboard_charts import history_caption, history_charts
    from spec_dashboard_history_views import history_tables, history_timeline
    from spec_dashboard_records import blob_link, github_sections, inventory_panel, safe_link
    from spec_dashboard_panels import definitions_panel, distribution, specs_panel, states_panel
    from spec_dashboard_structure import structure_panel
    from spec_dashboard_style import STYLE, panel, zones

__all__ = ['distribution', 'render']


def source_pattern(records):
    patterns = sorted({str(PurePosixPath(item['source']).parent.parent / '*' / PurePosixPath(item['source']).name)
                       for item in records})
    return ', '.join(patterns) or 'no status files'


def title_block(snapshot):
    repository, revision = snapshot['repository'], snapshot['revision']
    commit = safe_link(f'https://github.com/{repository}/commit/{revision}', revision[:12])
    cells = [('title', 'Title', '<b>Spec delivery: ' + html.escape(repository.split('/')[-1]) + '</b>'),
             ('', 'Repository', html.escape(repository)), ('', 'Commit', '<span class="mono">' + commit + '</span>'),
             ('', 'Captured (UTC)', '<span class="mono">' + html.escape(snapshot['captured_at'][:19]) + '</span>'),
             ('', 'Snapshot', '<a href="snapshot.json">snapshot.json</a> (v1)'),
             ('', 'Source', '<span class="mono">' + html.escape(source_pattern(snapshot['records'])) + '</span>'),
             ('', 'Sheet', '1 of 1')]
    return ('<section class="block" aria-label="Title block">'
            + ''.join(f'<div class="{css}"><small>{name}</small>{value}</div>' for css, name, value in cells) + '</section>')


def count_caption(snapshot):
    kinds = [item['kind'] for item in snapshot['records']]
    return f'{kinds.count("spec")} specs, {kinds.count("requirement")} requirements'


def current_panels(snapshot):
    records = snapshot['records']
    return [
        panel('A', 'Delivery structure', caption=html.escape(count_caption(snapshot)), body=structure_panel(snapshot)),
        panel('B', 'Delivery states', caption='count of total', body=states_panel(records)),
        panel('C', 'State definitions', caption='delivery_state', body=definitions_panel()),
        panel('D', 'Specifications', caption='specs/*/status.json',
              body=specs_panel(snapshot, blob_link(snapshot)), width='w7'),
    ]


def history_panels(snapshot):
    history = snapshot.get('history', {})
    return [
        panel('E', 'Observed delivery history', caption=html.escape(history_caption(history)),
              body=history_charts(history), width='w5'),
        panel('F', 'Timeline', caption='UTC commit dates',
              body=history_timeline(history, snapshot['captured_at']), width='w6'),
    ]


def audit_panels(snapshot):
    history = snapshot.get('history', {})
    return [
        panel('G', 'Open issues and pull requests', caption='open at capture', body=github_sections(snapshot), width='w6'),
        panel('H', 'Observed changes', caption='per commit',
              body=history_tables(history, snapshot['repository']), width='w5'),
        panel('J', 'Record inventory', caption=f'{len(snapshot["records"])} records', body=inventory_panel(snapshot)),
        title_block(snapshot),
    ]


def render(snapshot):
    title = html.escape(snapshot['repository'] + ': spec delivery')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><title>{title}</title>{STYLE}</head><body>'
            f'<div class="frame">{zones()}<main class="sheet">' + ''.join(current_panels(snapshot) + history_panels(snapshot) + audit_panels(snapshot))
            + '</main></div></body></html>')
