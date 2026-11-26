"""Pinned analyzer provisioning for the lint-type fixtures.

The gate never installs a tool while checking.  The tests provision the exact pinned
Ruff once per module when the environment lacks it, so the fixtures measure a real
analyzer without adding it to this repository's own lockfile.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import subprocess
from collections.abc import Iterator

import pytest

from pipelines_hooks.code import lint_type


def _version(path: str) -> str:
    out = subprocess.run([path, "--version"], capture_output=True, text=True, check=False).stdout
    match = re.search(r"\d+(?:\.\d+)+", out)
    return match.group(0) if match else ""


@pytest.fixture(scope="module", autouse=True)
def pinned_ruff(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    pin = lint_type.DEFAULT_TOOLS["ruff"]
    found = shutil.which("ruff")
    if found and _version(found) == pin:
        yield
        return
    base = tmp_path_factory.mktemp("ruff-tool")
    attempts = (
        ["uv", "tool", "install", "--tool-dir", str(base / "tools"), "--bin-dir", str(base / "bin"), f"ruff=={pin}"],
        ["uv", "pip", "install", "--python", sys.executable, "--target", str(base / "target"), f"ruff=={pin}"],
    )
    errors = []
    for argv in attempts:
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            break
        errors.append(f"{' '.join(argv[:3])}: {result.stderr[-600:]}")
    else:
        pytest.fail("cannot provision the pinned ruff: " + " | ".join(errors))
    bin_dir = base / "bin" if (base / "bin").is_dir() else base / "target" / "bin"
    patch = pytest.MonkeyPatch()
    patch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    try:
        yield
    finally:
        patch.undo()
