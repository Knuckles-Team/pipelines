"""PIPE-RELEASE-R012: transitional distribution aliases share one comparison table."""

from __future__ import annotations

import pytest

from pipelines_hooks.core.distributions import (
    AXIL,
    MEDULLA,
    MEDULLA_STEM,
    MERISTEM,
    NEW_DISTRIBUTIONS,
    OLD_DISTRIBUTIONS,
    OVERSTORY,
    SDK,
    TUIG,
    distribution_for,
    is_distribution,
    migration_distribution,
)

pytestmark = pytest.mark.spec("PIPE-RELEASE-R012")


@pytest.mark.parametrize("role", (SDK, MERISTEM, MEDULLA, MEDULLA_STEM, OVERSTORY, TUIG, AXIL))
def test_each_role_accepts_old_and_new_distribution_names(role: str) -> None:
    assert is_distribution(OLD_DISTRIBUTIONS[role], role)
    assert is_distribution(NEW_DISTRIBUTIONS[role], role)
    assert not is_distribution("unrelated-package", role)
    assert migration_distribution(role) == NEW_DISTRIBUTIONS[role]


def test_distribution_for_preserves_detected_spelling_and_defaults_old() -> None:
    assert distribution_for(["requests>=2", "scion-sdk[mcp]>=1"], SDK) == "scion-sdk"
    assert distribution_for(["requests>=2", "agent-connector-sdk[mcp]>=1"], SDK) == "agent-connector-sdk"
    assert distribution_for(["requests>=2"], SDK) == OLD_DISTRIBUTIONS[SDK]
