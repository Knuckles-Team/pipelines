"""A ``Spec: none (<reason>)`` trailer is one exemption, whatever punctuation the reason has."""

from __future__ import annotations

import pytest

from pipelines_hooks.specs.trailer_ids import named_ids


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_none_exemption_reason_may_contain_commas() -> None:
    assert named_ids(["none (merge main, typing)"]) == []


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_ids_still_split_on_commas() -> None:
    assert named_ids(["X-R001.1, R001.2, none (reason)"]) == ["X-R001.1", "X-R001.2"]
