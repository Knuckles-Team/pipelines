"""Receipt citations retain labels and link only valid relative paths."""
import html

import pytest

from scripts.spec_dashboard_records import evidence_links


@pytest.mark.parametrize(('receipt', 'target'), [
    ('tests/test_spec_dashboard_concepts.py:18', 'tests/test_spec_dashboard_concepts.py#L18'),
    ('tests/test_run.py:18-24', 'tests/test_run.py#L18-L24'),
    ('tests/test_run.py::TestRun::test_run[value:3]', 'tests/test_run.py'),
    ('tests/test_run.py:18::test_run', 'tests/test_run.py#L18'),
    ('tests/a b&<c>.py:2', 'tests/a%20b%26%3Cc%3E.py#L2'),
])
def test_receipt_line_and_pytest_forms(receipt, target):
    output = evidence_links({'repository': 'Knuckles-Team/demo', 'revision': 'a' * 40}, {'verified_by': [receipt]})
    assert '/blob/' + 'a' * 40 + '/' + target + '"' in output
    assert html.escape(receipt) + '</a>' in output


@pytest.mark.parametrize('receipt', [
    '/tmp/test.py:1', '../test.py:1', 'tests/../../test.py:1',
    'tests/test.py:0', 'tests/test.py:-1', 'tests/test.py:5-2',
    'tests/test.py:abc', 'tests/test.py#L1', 'https://example.invalid/test.py',
    'tests/./test.py:1', 'tests//test.py:1', 'tests/test.py\x00:1',
    r'tests\..\test.py:1',
])
def test_invalid_receipts_remain_unlinked(receipt):
    output = evidence_links({'repository': 'Knuckles-Team/demo', 'revision': 'a' * 40}, {'verified_by': [receipt]})
    assert output == html.escape(receipt)
