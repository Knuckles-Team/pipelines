"""Boundary accounting independent of the Git transport."""
from pathlib import Path
from scripts.spec_dashboard_sources import source_records
from scripts.spec_dashboard_history_metrics import observations
from scripts.spec_dashboard_history import source_kind
from scripts.spec_dashboard_charts import history_panels


def records(raw):
    items = source_records(raw, Path('specs/s/status.json'), 'spec')
    return {(item['kind'], item['parent'], item['id']): item for item in items}


def test_requirement_transition_never_completes_parent():
    baseline = {'spec_id': 'S', 'delivery_state': 'SPECIFIED', 'requirements': [
        {'id': 'R', 'delivery_state': 'BUILDING'}]}
    final = {**baseline, 'requirements': [{'id': 'R', 'delivery_state': 'LANDED', 'acceptance_state': 'ACCEPTED'}]}
    result = observations([('a', '2026-01-01T00:00:00Z', records(baseline)),
                           ('b', '2026-01-02T00:00:00Z', records(final))])
    point = result['points'][-1]
    assert point['spec']['completed'] == 0 and point['spec']['remaining'] == 1
    assert point['requirement']['completed'] == 1 and point['requirement']['remaining'] == 0


def test_acceptance_reversal_is_reopened_without_new_landing():
    before = records({'spec_id': 'S', 'delivery_state': 'LANDED', 'acceptance_state': 'ACCEPTED'})
    after = records({'spec_id': 'S', 'delivery_state': 'LANDED', 'acceptance_state': 'FAILED'})
    result = observations([('a', '2026-01-01T00:00:00Z', before), ('b', '2026-01-02T00:00:00Z', after)])
    assert result['points'][-1]['spec']['reopened'] == 1
    assert result['points'][-1]['spec']['landed'] == 0
    assert result['points'][-1]['spec']['remaining'] == 1


def test_scope_addition_and_removal_are_distinct_from_completions():
    added = records({'spec_id': 'S', 'delivery_state': 'LANDED', 'acceptance_state': 'ACCEPTED'})
    result = observations([('a', '2026-01-01T00:00:00Z', {}), ('b', '2026-01-02T00:00:00Z', added),
                           ('c', '2026-01-03T00:00:00Z', {})])
    assert result['points'][1]['spec']['added'] == 1
    assert result['points'][2]['spec']['removed'] == 1
    assert sum(point['spec']['completed'] for point in result['points']) == 0


def test_empty_scope_and_zero_velocity_render_honestly():
    result = observations([('a', '2026-01-01T00:00:00Z', {}), ('b', '2026-01-02T00:00:00Z', {})])
    result['truncated'] = False
    page = history_panels(result, 'owner/repo')
    assert 'nan' not in page.lower() and 'infinity' not in page.lower()
    assert result['points'][-1]['spec']['total'] == 0
    assert result['points'][-1]['spec']['landed'] == 0


def test_template_history_never_enters_scope():
    config = {'sources': [{'glob': 'specs/**/status.json'}]}
    assert source_kind(Path('specs/_template/status.json'), config) is None
    assert source_kind(Path('specs/real/status.json'), config) == 'spec'
