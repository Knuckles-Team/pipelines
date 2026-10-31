"""spec-standard: a behaviour row is complete enough to implement without assumptions."""

from __future__ import annotations

from pipelines_hooks.specs.completeness import check_complete_rows
from pipelines_hooks.specs.standard import ROW_PHRASES

FULL = (
    "| `X-A-R001` | **Answer.** Caller chain: `a.py:run` to `b.py:answer`. Shape: add `answer` in `b.py` "
    "using `helper`. | `tests/test_b.py::test_answer`. |\n"
)


def test_a_complete_row_is_clean() -> None:
    # spec: PIPE-GATES-R044
    assert check_complete_rows(FULL) == []


def test_a_row_without_a_caller_chain_shape_or_test_is_a_finding() -> None:
    # spec: PIPE-GATES-R044
    found = " ".join(check_complete_rows("| `X-A-R001` | **Answer.** It answers. | Looks right. |\n"))
    assert "'Caller chain:' sentence" in found
    assert "'Shape:' sentence" in found
    assert "test as path::name" in found


def test_tbd_is_a_finding() -> None:
    # spec: PIPE-GATES-R044
    row = FULL.replace("Answer.", "Answer TBD.")
    assert any("says TBD" in f for f in check_complete_rows(row))


def test_a_rollup_parent_and_a_retired_row_are_exempt() -> None:
    # spec: PIPE-GATES-R044
    text = "| `X-A-R001` | **Parent.** Rollup. | Children. |\n" + FULL.replace("R001", "R001.1")
    text += "| `X-A-R002` | **RETIRED: gone.** | none |\n"
    assert check_complete_rows(text) == []


def test_the_findings_fail_only_for_an_added_row() -> None:
    # spec: PIPE-GATES-R044
    assert any(p in "X-A-R001 behaviour row lacks a test as path::name" for p in ROW_PHRASES)
