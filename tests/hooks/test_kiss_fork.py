"""The kiss fork probe rejects the upstream 0.4.10 build that prints the same version."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.core import tools
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.kiss_fork import require_fork_build

UPSTREAM = "#!/bin/sh\necho 'missing module helper declared from src/a.rs'\nexit 1\n"
FORK = "#!/bin/sh\ntest -f src/a/tests/helper.rs || exit 3\necho 'NO VIOLATIONS'\n"


def _fake(tmp_path: Path, body: str) -> str:
    binary = tmp_path / "kiss"
    binary.write_text(body, encoding="utf-8")
    binary.chmod(0o755)
    return str(binary)


def test_probe_rejects_the_upstream_build(tmp_path: Path) -> None:
    with pytest.raises(CannotRun, match="not the pinned kiss fork build"):
        require_fork_build(_fake(tmp_path, UPSTREAM))


def test_probe_accepts_a_build_that_resolves_the_inline_module(tmp_path: Path) -> None:
    require_fork_build(_fake(tmp_path, FORK))


def test_verified_kiss_runs_the_probe_after_the_version_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fake(tmp_path, "#!/bin/sh\necho 'kiss 0.4.10'\n")
    monkeypatch.setenv("KISS_BIN", binary)
    probed: list[str] = []
    monkeypatch.setitem(tools._BUILD_PROBES, "kiss", probed.append)
    assert tools.verified("kiss") == binary
    assert probed == [binary]
