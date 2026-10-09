"""Milestone timeline and per-commit audit tables for observed Git status history."""
import html

if __package__:
    from .spec_dashboard_charts import daily_velocity, unavailable
else:
    from spec_dashboard_charts import daily_velocity, unavailable


def milestones(history, captured_at):
    counts = daily_velocity(history['points'], 'requirement')
    peaks = sorted(sorted(counts, key=lambda pair: -pair[1])[:3])
    first = history['points'][0]['observed_at'][:10]
    items = [(first, 'First observed commit')]
    items += [(day, f'{count} requirement lands' if count == 1 else f'{count} requirements land') for day, count in peaks if count]
    return items + [(captured_at[:10], 'Snapshot capture')]


def history_timeline(history, captured_at):
    if not history.get('available'):
        return unavailable(history)
    cells = ''.join(f'<div class="mile"><b>{html.escape(day)}</b><i></i>{html.escape(text)}</div>'
                    for day, text in milestones(history, captured_at))
    return ('<div class="timeline">' + cells + '</div><div class="note"><p>The dates are commit observations.</p>'
            '<p>No release or deployment timeline is available. Git status changes do not give release evidence.</p></div>')


def history_table(history, repository):
    rows = []
    for point in history['points']:
        for kind in ('spec', 'requirement'):
            values = point[kind]
            cells = [point['observed_at'], kind, *[values[key] for key in
                     ('total', 'remaining', 'unknown', 'added', 'removed', 'landed', 'completed', 'reopened')]]
            url = html.escape(f'https://github.com/{repository}/commit/{point["commit"]}', quote=True)
            rows.append('<tr><td class="mono"><a href="' + url + '">' + point['commit'][:8] + '</a></td>'
                        + ''.join('<td>' + html.escape(str(cell)) + '</td>' for cell in cells) + '</tr>')
    return (f'<details><summary>Scope per commit <span class="mono">({len(rows)} rows)</span></summary>'
            '<div class="scroll"><table><thead><tr>'
            '<th>Commit</th><th>Observed at</th><th>Kind</th><th>Scope</th><th>Remaining</th><th>Unknown</th>'
            '<th>Added</th><th>Removed</th><th>Landed</th><th>Accepted done</th><th>Reopened</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></details>')


def timeline(history):
    rows = []
    for event in history['events']:
        cells = [event[key] for key in ('observed_at', 'kind', 'id', 'parent', 'before', 'after')]
        rows.append('<tr>' + ''.join('<td>' + html.escape(str(cell)) + '</td>' for cell in cells) + '</tr>')
    return (f'<details><summary>State changes per commit <span class="mono">({len(rows)} events)</span></summary>'
            '<div class="scroll"><table><thead><tr>'
            '<th>Observed at</th><th>Kind</th><th>ID</th><th>Parent</th><th>Before</th><th>After</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></details>')


def history_tables(history, repository):
    if not history.get('available'):
        return unavailable(history)
    return ('<p>Each commit gives one observation. The tables show scope, reopened records and accepted-done changes.</p>'
            + history_table(history, repository) + timeline(history))
