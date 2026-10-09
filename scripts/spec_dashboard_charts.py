"""Inline SVG burndown and velocity charts for observed Git status history."""
import html
from collections import Counter
from datetime import datetime, timezone

LEFT, RIGHT, TOP, BOTTOM = 34, 332, 10, 128
NOUNS = {'spec': 'specs', 'requirement': 'requirements'}


def frame_lines(maximum):
    middle = (TOP + BOTTOM) / 2
    half = f'{maximum / 2:g}'
    return (f'<line class="grid" x1="{LEFT}" x2="{RIGHT}" y1="{TOP}" y2="{TOP}"/>'
            f'<line class="grid" x1="{LEFT}" x2="{RIGHT}" y1="{middle}" y2="{middle}"/>'
            f'<line class="axis" x1="{LEFT}" x2="{RIGHT}" y1="{BOTTOM}" y2="{BOTTOM}"/>'
            f'<line class="axis" x1="{LEFT}" x2="{LEFT}" y1="{TOP}" y2="{BOTTOM}"/>'
            f'<text x="{LEFT - 4}" y="{TOP + 3}" text-anchor="end">{maximum}</text>'
            f'<text x="{LEFT - 4}" y="{middle + 3}" text-anchor="end">{half}</text>'
            f'<text x="{LEFT - 4}" y="{BOTTOM + 3}" text-anchor="end">0</text>')


def axis_labels(first, last):
    return (f'<text x="{LEFT}" y="{BOTTOM + 14}">{html.escape(first)}</text>'
            f'<text x="{RIGHT}" y="{BOTTOM + 14}" text-anchor="end">{html.escape(last)}</text>')


def figure(label, body):
    escaped = html.escape(label)
    return (f'<figure><figcaption>{escaped}</figcaption><svg role="img" aria-label="{escaped}" '
            f'viewBox="0 0 340 148">{body}</svg></figure>')


def line_chart(points, kind):
    maximum = max((point[kind]['total'] for point in points), default=0) or 1
    step = (RIGHT - LEFT) / max(1, len(points) - 1)
    paths = []
    for field, css in [('total', 'scope'), ('remaining', 'remain')]:
        coordinates = ' '.join(f'{LEFT + i * step:.1f},{BOTTOM - point[kind][field] * (BOTTOM - TOP) / maximum:.1f}'
                               for i, point in enumerate(points))
        paths.append(f'<polyline class="{css}" points="{coordinates}"/>')
    label = f'{kind.title()} burndown. Blue line: remaining. Grey line: total scope.'
    return figure(label, frame_lines(maximum) + ''.join(paths)
                  + axis_labels('commit 1', f'commit {len(points)} (current)'))


def daily_velocity(points, kind):
    counts = Counter()
    for point in points:
        day = datetime.fromisoformat(point['observed_at']).astimezone(timezone.utc).date().isoformat()
        counts[day] += point[kind]['landed']
    return sorted(counts.items())


def velocity_chart(points, kind):
    counts = daily_velocity(points, kind)
    maximum = max((count for _, count in counts), default=0) or 1
    width = (RIGHT - LEFT) / max(1, len(counts))
    bars = []
    for index, (day, count) in enumerate(counts):
        height = count * (BOTTOM - TOP) / maximum
        bars.append(f'<rect class="vbar" x="{LEFT + index * width + 1:.1f}" y="{BOTTOM - height:.1f}" '
                    f'width="{max(1, width - 2):.1f}" height="{height:.1f}"><title>{day}: {count} '
                    f'newly source-landed</title></rect>')
    label = f'{kind.title()} velocity. Bars: new source-landed {NOUNS[kind]} per UTC commit date.'
    first, last = (counts[0][0], counts[-1][0]) if counts else ('No observations', '')
    return figure(label, frame_lines(maximum) + ''.join(bars) + axis_labels(first, last))


def unavailable(history):
    return '<p>History is not available: ' + html.escape(history.get('reason', 'No verified commit window')) + '</p>'


def history_charts(history):
    if not history.get('available'):
        return unavailable(history)
    points = history['points']
    window = ('The history window has a limit or a shallow clone. Earlier history is unknown.' if history['truncated']
              else 'The history uses all available first-parent commits.')
    charts = ''.join(line_chart(points, kind) + velocity_chart(points, kind) for kind in ('spec', 'requirement'))
    return ('<div class="charts">' + charts + '</div><div class="note">'
            f'<p>{window} {html.escape(history["baseline"])}</p>'
            '<p>Remaining is all work that is not accepted as done. It includes unknown states.</p>'
            '<p>The grey scope line can go up or down. Removed scope is not completion.</p>'
            '<p>Velocity counts only changes from a non-landed state to LANDED or CLOSED. '
            'Bars show only dates with observed commits. Panel H gives the exact counts.</p></div>')


def history_caption(history):
    if not history.get('available'):
        return 'not available'
    return f'first-parent, {history.get("sampled_commits", len(history["points"]))} commits'
