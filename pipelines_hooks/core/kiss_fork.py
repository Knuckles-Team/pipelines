"""Prove an installed kiss is the fleet's pinned fork build, not crates.io 0.4.12.

The fleet runs kiss 0.4.12 from the fork commit below: upstream 0.4.12 plus the
inline-module resolution fix (upstream PR dsweet99/kiss#48). Both builds print
``kiss 0.4.12``, so ``--version`` cannot tell them apart. The probe runs a
four-file crate that declares ``mod helper;`` inside an inline
``mod tests { .. }`` block of a non-root file: every upstream build through
0.4.12 aborts with ``missing module helper``; the pinned fork analyzes it
cleanly.

Install the pinned build with::

    cargo install --locked --git https://github.com/Knucklessg1/kiss \\
        --rev <KISS_FORK_REV> kiss-ai
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env

KISS_FORK_GIT = "https://github.com/Knucklessg1/kiss"
KISS_FORK_REV = "7f1c6785697d3fe9a41ceb8b8e5d0f615fb1f3d9"

_PROBE_CRATE = {
    "Cargo.toml": '[package]\nname = "inline_mod_probe"\nversion = "0.1.0"\nedition = "2024"\n',
    "src/lib.rs": "pub mod a;\n",
    "src/a.rs": "pub fn a() {}\n\n#[cfg(test)]\nmod tests {\n    mod helper;\n}\n",
    "src/a/tests/helper.rs": "#[test]\nfn h() {}\n",
}


def _write_probe(root: Path) -> None:
    for relative, text in _PROBE_CRATE.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def require_fork_build(executable: str) -> None:
    """Exit 2 (CannotRun) unless ``executable`` resolves inline-module children."""
    with tempfile.TemporaryDirectory(prefix="kiss-fork-probe-") as tmp:
        _write_probe(Path(tmp))
        try:
            result = subprocess.run(
                [executable, "check", "--lang", "rust", "."],
                cwd=tmp,
                env=sanitized_env(),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            raise CannotRun(f"could not run the kiss fork probe with {executable}: {exc}") from exc
    output = f"{result.stdout or ''}{result.stderr or ''}"
    if result.returncode != 0 or "missing module" in output:
        raise CannotRun(
            f"{executable} is not the pinned kiss fork build ({KISS_FORK_GIT} @ {KISS_FORK_REV}): "
            f"the inline-module probe failed with exit {result.returncode}: {output.strip()[-300:]}"
        )
