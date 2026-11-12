"""PIPE-RELEASE-R012: each ecosystem role has exactly one accepted distribution name."""

from __future__ import annotations

import pytest

from pipelines_hooks.core.distributions import (
    AXIL,
    DISTRIBUTIONS,
    MEDULLA,
    MERISTEM,
    OVERSTORY,
    SDK,
    TUIG,
    distribution,
    distribution_for,
    is_distribution,
)

pytestmark = pytest.mark.spec("PIPE-RELEASE-R012")

RETIRED = {
    SDK: "agent-connector-sdk",
    MERISTEM: "agent-utilities",
    MEDULLA: "epistemic-graph",
    OVERSTORY: "agent-webui",
    TUIG: "agent-terminal-ui",
    AXIL: "geniusbot",
}


@pytest.mark.parametrize("role", (SDK, MERISTEM, MEDULLA, OVERSTORY, TUIG, AXIL))
def test_each_role_accepts_only_the_current_distribution_name(role: str) -> None:
    assert distribution(role) == DISTRIBUTIONS[role]
    assert is_distribution(DISTRIBUTIONS[role], role)
    assert not is_distribution(RETIRED[role], role)
    assert not is_distribution("unrelated-package", role)


def test_distribution_for_recognises_only_the_current_name() -> None:
    assert distribution_for(["requests>=2", "scion-sdk[mcp]>=1"], SDK) == "scion-sdk"
    assert distribution_for(["requests>=2", "agent-connector-sdk[mcp]>=1"], SDK, default="x-y") == "x-y"
    assert distribution_for(["requests>=2"], SDK) == "scion-sdk"


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValueError):
        distribution("nope")
