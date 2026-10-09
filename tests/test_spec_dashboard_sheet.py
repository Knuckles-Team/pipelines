"""Drawing-sheet layout: lettered panels, zone frame, title block and self-contained output."""
import re
from pathlib import Path

from scripts.spec_dashboard import record, render
from scripts.spec_dashboard_panels import specs_panel, ticks


def snapshot():
    spec = record({'spec_id': 'S-1', 'delivery_state': 'SPECIFIED', 'title': 'Spec one'},
                  Path('specs/one/status.json'), 'spec')
    landed = record({'id': 'R1', 'delivery_state': 'LANDED', 'acceptance_state': 'ACCEPTED'},
                    Path('specs/one/status.json'), 'requirement', parent='S-1')
    building = record({'id': 'R2', 'delivery_state': 'BUILDING'}, Path('specs/one/status.json'),
                      'requirement', parent='S-1')
    return {'repository': 'owner/repo', 'revision': 'a' * 40, 'captured_at': '2026-01-02T03:04:05+00:00',
            'records': [spec, landed, building], 'github': {'issues': {'available': True, 'items': []}}}


def test_sheet_has_lettered_panels_zones_and_title_block():
    page = render(snapshot())
    for letter, title in [('A', 'Delivery structure'), ('B', 'Delivery states'), ('C', 'State definitions'),
                          ('D', 'Specifications'), ('E', 'Observed delivery history'), ('F', 'Timeline'),
                          ('G', 'Open issues and pull requests'), ('H', 'Observed changes'), ('J', 'Record inventory')]:
        assert f'<span class="tab">{letter}</span><h2 id="panel-{letter}">{title}</h2>' in page
    assert page.count('<span>8</span>') == 2 and page.count('<span>D</span>') == 2
    assert 'Sheet</small>1 of 1' in page and 'specs/*/status.json' in page
    assert 'prefers-color-scheme:dark' in page


def test_sheet_is_self_contained():
    page = render(snapshot())
    assert '<script' not in page
    assert not re.search(r'<link[^>]+href=', page)
    assert not re.search(r'src="https?://', page)


def test_states_use_glyph_and_word_not_colour_alone():
    page = render(snapshot())
    assert '&#10003; Landed' in page and '&#10005; Not landed' in page and '&#10003; Done' in page
    assert 'BUILDING (in-progress)' in page and '1 of 2 requirements' in page


def test_spec_table_counts_landed_and_done_from_requirements():
    rows = specs_panel(snapshot(), lambda item, label: label)
    assert 'S-1' in rows and 'Spec one' in rows
    assert '<td class="n">2</td><td class="n">1/2</td><td class="n">1</td>' in rows
    assert specs_panel({'records': []}, None) == '<p>No documented records.</p>'


def test_tick_scale_ends_on_total():
    assert ticks(9) == [0, 2, 4, 6, 8, 9]
    assert ticks(489) == [0, 100, 200, 300, 400, 489]
    assert ticks(1) == [0, 1]
