"""The contract-coverage rollup row is proven by its child rows."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SPEC = Path(__file__).resolve().parents[1] / "specs" / "gates"
CHILD = re.compile(r"^\| `(PIPE-GATES-R034\.\d+)` ", re.M)


@pytest.mark.spec("PIPE-GATES-R034")
def test_every_contract_coverage_child_row_has_a_test_spec_entry() -> None:
    children = CHILD.findall((SPEC / "requirements.md").read_text(encoding="utf-8"))
    assert children, "the rollup row has child rows"
    test_spec = (SPEC / "test-spec.md").read_text(encoding="utf-8")
    assert [c for c in children if c not in test_spec] == []
