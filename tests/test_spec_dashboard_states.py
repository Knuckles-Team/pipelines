"""The delivery page shows three states only (PIPE-PAGES-R017)."""
import re
from pathlib import Path

import pytest

from scripts.spec_dashboard import record, render
from scripts.spec_dashboard_panels import definitions_panel


def snapshot(*states):
    path = Path('specs/one/status.json')
    spec = record({'spec_id': 'S-1', 'delivery_state': 'SPECIFIED', 'title': 'Spec one'}, path, 'spec')
    rows = [record({'id': f'R{n}', 'delivery_state': state}, path, 'requirement', parent='S-1')
            for n, state in enumerate(states)]
    return {'repository': 'owner/repo', 'revision': 'a' * 40, 'captured_at': '2026-01-02T03:04:05+00:00',
            'records': [spec, *rows], 'github': {'issues': {'available': True, 'items': []}}}


@pytest.mark.spec("PIPE-PAGES-R017.1")
def test_legend_has_three_states():
    legend = definitions_panel()
    assert re.findall(r'<td class="mono">([A-Z_]+)</td>', legend) == ['SPECIFIED', 'LANDED', 'VERIFIED']
    assert 'ACCEPTED' not in legend and 'CLOSED' not in legend


@pytest.mark.spec("PIPE-PAGES-R017.2")
def test_row_has_one_state_cell():
    page = render(snapshot('LANDED'))
    row = re.search(r'<tr id="spec-S-1">.*?</tr>', page, re.S).group(0)
    assert row.count('class="mono"') == 2 and 'NOT_AUDITED' not in page
    assert 'Acceptance' not in page and 'Release' not in page


@pytest.mark.spec("PIPE-PAGES-R017.3")
def test_unknown_state_renders_invalid():
    page = render(snapshot('BUILDING', 'VERIFIED'))
    assert 'INVALID' in page and 'BUILDING' not in page
    assert 'id="invalid-count">1<' in page
