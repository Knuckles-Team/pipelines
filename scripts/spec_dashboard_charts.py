"""Inline SVG charts and audit table for observed Git status history."""
from collections import Counter
from datetime import datetime, timezone
import html


def line_chart(points, kind):
    maximum = max((point[kind]['total'] for point in points), default=0) or 1
    paths = []
    for field, color in [('total', '#777'), ('remaining', '#245fc0')]:
        coordinates = ' '.join(f'{40+i*620/max(1,len(points)-1):.1f},{170-point[kind][field]*140/maximum:.1f}'
                               for i, point in enumerate(points))
        paths.append(f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="3"/>')
    label = html.escape(kind.title() + ' burndown: blue remaining, gray total scope')
    return (f'<h3>{label}</h3><svg role="img" aria-label="{label}" viewBox="0 0 720 210">'
            f'<text x="4" y="30">{maximum}</text><text x="4" y="175">0</text>'
            + ''.join(paths) + '<text x="40" y="200">First observed commit → current commit (sequence)</text></svg>')


def daily_velocity(points, kind):
    counts = Counter()
    for point in points:
        day = datetime.fromisoformat(point['observed_at']).astimezone(timezone.utc).date().isoformat()
        counts[day] += point[kind]['landed']
    return sorted(counts.items())


def velocity_chart(points, kind):
    counts = daily_velocity(points, kind)
    maximum = max((count for _, count in counts), default=0) or 1
    width = 620 / max(1, len(counts))
    bars = []
    for index, (day, count) in enumerate(counts):
        height = count * 140 / maximum
        bars.append(f'<rect x="{40+index*width:.1f}" y="{170-height:.1f}" width="{max(1,width-2):.1f}" '
                    f'height="{height:.1f}" fill="#245fc0"><title>{day}: {count} newly source-landed</title></rect>')
    label = html.escape(kind.title() + ' velocity: observed transitions to source-landed per UTC commit date')
    dates = 'No observations' if not counts else counts[0][0] + ' → ' + counts[-1][0]
    return (f'<h3>{label}</h3><svg role="img" aria-label="{label}" viewBox="0 0 720 210">'
            f'<text x="4" y="30">{maximum}</text><text x="4" y="175">0</text>'
            + ''.join(bars) + f'<text x="40" y="200">{dates}</text></svg>')


def history_table(history, repository):
    rows = []
    for point in history['points']:
        for kind in ('spec', 'requirement'):
            values = point[kind]
            cells = [point['observed_at'], kind, *[values[key] for key in
                     ('total', 'remaining', 'unknown', 'added', 'removed', 'landed', 'completed', 'reopened')]]
            url = html.escape(f'https://github.com/{repository}/commit/{point["commit"]}', quote=True)
            rows.append('<tr><td><a href="' + url + '">' + point['commit'][:8] + '</a></td>'
                        + ''.join('<td>' + html.escape(str(cell)) + '</td>' for cell in cells) + '</tr>')
    return ('<details><summary>Observed history and scope accounting</summary><section><table><thead><tr>'
            '<th>Commit</th><th>Observed at</th><th>Kind</th><th>Scope</th><th>Remaining</th><th>Unknown</th>'
            '<th>Added</th><th>Removed</th><th>Landed</th><th>Accepted done</th><th>Reopened</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></section></details>')


def timeline(history):
    rows = []
    for event in history['events']:
        cells = [event[key] for key in ('observed_at', 'kind', 'id', 'parent', 'before', 'after')]
        rows.append('<tr>' + ''.join('<td>' + html.escape(str(cell)) + '</td>' for cell in cells) + '</tr>')
    return ('<details><summary>Commit-observed delivery timeline</summary><section><table><thead><tr>'
            '<th>Observed at</th><th>Kind</th><th>ID</th><th>Parent</th><th>Before</th><th>After</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></section></details>')


def history_panels(history, repository):
    if not history.get('available'):
        return '<h2>Velocity and burndown</h2><p>History unavailable: ' + html.escape(
            history.get('reason', 'No verified commit window')) + '</p>'
    points = history['points']
    bounded = 'Bounded or shallow window; earlier history is unknown.' if history['truncated'] else 'Available first-parent history.'
    charts = ''.join(line_chart(points, kind) + velocity_chart(points, kind) for kind in ('spec', 'requirement'))
    return ('<h2>Observed delivery history</h2><p>' + bounded + ' '
            + html.escape(history['baseline']) + '</p><p>Commit dates are observation times, not release or deployment dates. '
            'Remaining means not explicitly accepted as done, including unknown states. Gray scope can grow or shrink; '
            'removed scope is not completion. Velocity counts only transitions from an observed non-landed state to '
            'LANDED/CLOSED. Reopened records and accepted-done transitions are separately tabulated. '
            'Bars include dates with observed commits; the table provides exact counts.</p>'
            + charts + history_table(history, repository) + timeline(history)
            + '<p>Release/deployment timeline remains unavailable: no release evidence is inferred from Git status changes.</p>')
