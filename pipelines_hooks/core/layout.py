"""Where a consuming repository keeps each shared-gate input: under ``.config/``.

The repository root carries only what a tool can discover nowhere else. Every
input a shared gate reads has one canonical home in ``.config/``; the retired
root location is rejected loudly (exit 2) instead of being silently ignored,
so a half-migrated repository can never run a gate against an empty ledger.
"""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

CONFIG_DIR = ".config"
REPO_LAYOUT = f"{CONFIG_DIR}/repo-layout.toml"
KISS_CONFIG = f"{CONFIG_DIR}/kiss.toml"
DUPEHOUND_DISTINCT = f"{CONFIG_DIR}/dupehound-distinct.toml"

#: Canonical path -> the retired root location it replaced.
RETIRED = {
    REPO_LAYOUT: ".repo-layout.toml",
    KISS_CONFIG: ".kiss/kiss.toml",
    DUPEHOUND_DISTINCT: "dupehound-distinct.toml",
}


def located(root: Path, canonical: str) -> Path:
    """``root / canonical``, failing closed while the retired root copy still exists."""
    retired = root / RETIRED[canonical]
    if retired.exists() or retired.is_symlink():
        raise CannotRun(f"{RETIRED[canonical]} moved to {canonical}; move the file (git mv) and repoint its consumers")
    return root / canonical
