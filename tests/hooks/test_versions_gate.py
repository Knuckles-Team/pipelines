"""The scanner-version gate accepts an omitted or explicit tool selection."""

from __future__ import annotations

import pytest

from pipelines_hooks.core import versions_gate
from pipelines_hooks.core.tools import PINNED_VERSIONS


def test_no_arguments_verify_every_pinned_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified: list[str] = []
    monkeypatch.setattr(
        versions_gate, "verified", lambda tool: verified.append(tool) or f"/bin/{tool}"
    )

    assert versions_gate.main([]) == 0
    assert verified == sorted(PINNED_VERSIONS)


def test_unknown_scanner_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        versions_gate,
        "verified",
        lambda tool: pytest.fail(f"unexpected verification: {tool}"),
    )

    with pytest.raises(SystemExit, match="2"):
        versions_gate.main(["not-a-scanner"])
