"""The advisory workflow keys its scanner cache on every provisioning input and stays advisory."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((REPO / ".github/workflows/advisory_pipeline.yml").read_text())
STEPS = WORKFLOW["jobs"]["advisory"]["steps"]
KEYED_INPUTS = (
    "scripts/install_scanners.sh",
    "scripts/install_jscpd.py",
    "scripts/patches/jscpd-markdown-glob.patch",
    "pipelines_hooks/core/jscpd_build.py",
)


def _step(name: str) -> dict:
    return next(item for item in STEPS if item["name"] == name)


def test_cache_identity_covers_every_provisioning_input() -> None:
    fetch = _step("Fetch the pipelines revision of this workflow")
    assert all(path in fetch["run"] for path in KEYED_INPUTS)
    assert "SCANNER_ROOT=$RUNNER_TEMP/pipelines-scanners" in fetch["run"]
    restore = next(item for item in STEPS if item.get("id") == "scanner-cache")
    save = _step("Save pinned scanner toolchain")
    assert restore["with"]["path"] == save["with"]["path"] == "${{ env.SCANNER_ROOT }}"
    assert restore["with"]["key"] == "pipelines-scanners-${{ runner.os }}-${{ runner.arch }}-${{ env.SCANNER_KEY }}"
    assert save["with"]["key"] == "${{ steps.scanner-cache.outputs.cache-primary-key }}"


def test_cache_hits_still_prove_the_scanners() -> None:
    on_path = _step("Put scanners on PATH")
    assert "cache-hit" not in on_path.get("if", "")
    assert 'install_scanners.sh" "$SCANNER_ROOT" >> "$GITHUB_PATH"' in on_path["run"]


def test_the_advisory_workflow_never_fails_and_only_reads() -> None:
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert WORKFLOW["jobs"]["advisory"]["permissions"] == {"contents": "read"}
    report = _step("Write the advisory report")
    assert report["run"].rstrip().endswith("exit 0")
    assert "set -e" not in report["run"].replace("set -uo pipefail", "")
    for step in STEPS:
        if step["name"] not in {
            "Checkout",
            "Install uv",
            "Fetch the pipelines revision of this workflow",
            "Write the advisory report",
        }:
            assert step.get("continue-on-error") is True, step["name"]
