"""scripts/install_scanners.sh installs exactly the scanner builds the hooks verify."""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.core.kiss_fork import KISS_FORK_GIT, KISS_FORK_REV
from pipelines_hooks.core.tools import PINNED_VERSIONS

INSTALLER = (Path(__file__).resolve().parents[2] / "scripts" / "install_scanners.sh").read_text(encoding="utf-8")


def test_installer_builds_the_pinned_kiss_fork() -> None:
    assert f"--git {KISS_FORK_GIT} --rev {KISS_FORK_REV} kiss-ai" in INSTALLER


def test_installer_pins_the_versions_the_hooks_verify() -> None:
    assert f"--version {PINNED_VERSIONS['dupehound']} dupehound" in INSTALLER
    assert f'"jscpd@{PINNED_VERSIONS["jscpd"]}"' in INSTALLER


def test_installer_covers_every_pinned_scanner() -> None:
    for tool in PINNED_VERSIONS:
        assert f"{tool}/bin" in INSTALLER or f".bin/{tool}" in INSTALLER, tool
