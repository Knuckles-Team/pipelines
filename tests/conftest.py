"""Suite-wide fixtures."""

from __future__ import annotations

import pytest

from tests.git_fixture_environment import ROUTING


@pytest.fixture(autouse=True)
def _no_ambient_git_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the repository selectors a git hook exports (GIT_DIR, GIT_INDEX_FILE, ...).

    Under pre-commit or pre-push the suite inherits them, and a test that runs
    ``git`` in a temporary repository would otherwise write the calling
    repository's index (a pre-push once staged the deletion of every file).
    A test that needs one sets it with ``monkeypatch``.
    """
    for key in ROUTING:
        monkeypatch.delenv(key, raising=False)
