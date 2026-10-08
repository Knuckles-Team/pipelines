"""Cache paths must be canonical before Actions glob validation sees them."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text())
STEPS = WORKFLOW["jobs"]["pre-commit"]["steps"]


@pytest.mark.parametrize("name", ["checkout", "checkout with spaces", "checkout-$(false)"])
def test_cache_root_is_canonical_before_restore(tmp_path, name):
    workspace = tmp_path / name
    workspace.mkdir()
    environment = tmp_path / "github-env"
    step = next(item for item in STEPS if item["name"] == "Resolve scanner cache directory")
    assert STEPS.index(step) < next(i for i, item in enumerate(STEPS) if item.get("id") == "scanner-cache")
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]], check=True,
        env={**os.environ, "GITHUB_WORKSPACE": str(workspace), "GITHUB_ENV": str(environment)},
    )
    assignment, root = environment.read_text().strip().split("=", 1)
    assert assignment == "SCANNER_ROOT"
    assert root == str((workspace / ".." / "pipelines-scanners").resolve())
    assert Path(root).is_absolute()
    assert not {".", ".."}.intersection(root.split("/"))
    assert not Path(root).exists()  # Resolution must also work on the first cache miss.


def test_cache_identity_and_validation_are_preserved():
    restore = next(item for item in STEPS if item.get("id") == "scanner-cache")
    save = next(item for item in STEPS if item["name"] == "Save pinned scanner toolchain")
    assert restore["with"]["path"] == save["with"]["path"] == "${{ env.SCANNER_ROOT }}"
    assert restore["with"]["key"] == (
        "pipelines-scanners-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles("
        "'scripts/install_scanners.sh', 'scripts/install_jscpd.py', "
        "'scripts/patches/jscpd-markdown-glob.patch', 'pipelines_hooks/core/jscpd_build.py') }}"
    )
    assert save["with"]["key"] == "${{ steps.scanner-cache.outputs.cache-primary-key }}"
    validate = next(item for item in STEPS if item["name"] == "Put scanners on PATH and resolve the diff base")
    assert "if" not in validate  # Cache hits still run the provenance/behavior checks.
    assert 'bash scripts/install_scanners.sh "$SCANNER_ROOT" >> "$GITHUB_PATH"' in validate["run"]
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert WORKFLOW["jobs"]["pre-commit"]["permissions"] == {"contents": "read"}
