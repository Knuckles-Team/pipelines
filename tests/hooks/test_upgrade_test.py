"""upgrade-test: stored data upgrades in place from the last production release (PIPE-RELEASE-R030)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.cli import run_gate
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.release import upgrade_test as ut
from tests.hooks.conftest import Repo

DECLARATION = {
    "package": "pkg",
    "fixtures": [{"kind": "records", "write": ["w", "{data}"], "read": ["r", "{data}"]}],
}


class Env:
    """A fake installer and runner: the data file holds the writer's format, the reader needs the installed version to know it."""

    def __init__(self, reads_old: bool) -> None:
        self.reads_old = reads_old
        self.installed: list[str] = []

    def install(self, venv: Path, spec: str) -> None:
        self.installed.append(spec)

    def execute(self, argv):
        data = Path(argv[1])
        if argv[0] == "w":
            (data / "records").write_text(self.installed[-1])
            return 0, ""
        if self.reads_old or self.installed[-1] == "pkg==1.0.0":
            return 0, ""
        return 1, "unknown record format " + (data / "records").read_text()


# spec: PIPE-RELEASE-R030
def test_a_failed_read_after_upgrade_blocks_the_release() -> None:
    env = Env(reads_old=False)
    failures = ut.run(DECLARATION, "1.0.0", "pkg-2.0.0.whl", env.install, env.execute)
    assert env.installed == ["pkg==1.0.0", "pkg-2.0.0.whl"]
    assert len(failures) == 1
    assert "records" in failures[0] and "1.0.0" in failures[0] and "read failed" in failures[0]


# spec: PIPE-RELEASE-R030
def test_a_clean_upgrade_passes(repo: Repo) -> None:
    env = Env(reads_old=True)
    assert ut.run(DECLARATION, "1.0.0", "pkg-2.0.0.whl", env.install, env.execute) == []
    # The default from-version is the latest production tag; with none, the gate cannot run (exit 2).
    assert run_gate("upgrade-test", ["--root", str(repo.root), "--candidate", "x.whl"]) == 2
    repo.git("tag", "v1.9.0")
    repo.git("tag", "v1.10.0")
    repo.git("tag", "v2.0.0rc1")
    assert ut.latest_production_tag(repo.root) == "1.10.0"


def test_an_undeclared_fixture_set_cannot_run() -> None:
    with pytest.raises(CannotRun):
        ut.run({"package": "pkg"}, "1.0.0", "x", lambda *_: None, lambda *_: (0, ""))
