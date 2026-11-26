"""PIPE-GATES-R064: every unit of a multi-unit workspace builds and tests alone."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rust_per_unit  # noqa: E402

WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/gates_pipeline.yml").read_text(encoding="utf-8"))
METADATA = {
    "workspace_members": ["path+file:///w/core#0.1.0", "path+file:///w/app#0.1.0"],
    "packages": [
        {"id": "path+file:///w/core#0.1.0", "name": "core"},
        {"id": "path+file:///w/app#0.1.0", "name": "app"},
        {"id": "registry+https://index/serde#1.0.0", "name": "serde"},
    ],
}
# A fake cargo that fails `test` for the unit named "broken".
FAKE_CARGO = """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
sys.exit(101 if args[0] == "test" and args[args.index("-p") + 1] == "broken" else 0)
"""


# spec: PIPE-GATES-R064
def test_the_matrix_lists_every_workspace_unit() -> None:
    units = rust_per_unit.units_from_metadata(METADATA)
    assert units == ["app", "core"]  # members only; a dependency is no unit
    assert rust_per_unit.matrix(units) == {"include": [{"unit": "app"}, {"unit": "core"}]}
    single = {"workspace_members": ["a"], "packages": [{"id": "a", "name": "only"}]}
    assert rust_per_unit.units_from_metadata(single) == []
    job = WORKFLOW["jobs"]["rust-units"]
    assert job["outputs"]["matrix"] == "${{ steps.units.outputs.matrix }}"
    assert 'rust_per_unit.py" matrix' in "".join(step.get("run", "") for step in job["steps"])


# spec: PIPE-GATES-R064
def test_each_unit_runs_with_all_features_and_p() -> None:
    assert rust_per_unit.unit_commands("core") == [
        ["cargo", "build", "--all-features", "-p", "core"],
        ["cargo", "test", "--all-features", "-p", "core"],
    ]
    job = WORKFLOW["jobs"]["per-unit"]
    assert job["strategy"]["matrix"] == "${{ fromJSON(needs.rust-units.outputs.matrix) }}"
    assert job["strategy"]["fail-fast"] is False
    assert job["name"] == "per-unit ${{ matrix.unit }}"
    assert 'run --unit "$UNIT"' in "".join(step.get("run", "") for step in job["steps"])


# spec: PIPE-GATES-R064
def test_a_failing_unit_fails_the_aggregate(tmp_path: Path, capsys) -> None:
    cargo = tmp_path / "cargo"
    cargo.write_text(FAKE_CARGO, encoding="utf-8")
    cargo.chmod(0o755)
    assert rust_per_unit.run_unit("healthy", str(cargo)) == 0
    assert rust_per_unit.run_unit("broken", str(cargo)) == 1
    assert "PER_UNIT_FAILED: broken: cargo test --all-features -p broken" in capsys.readouterr().err
    # The job carries no continue-on-error, so its failure fails the called workflow and the caller's aggregate.
    assert not any("continue-on-error" in WORKFLOW["jobs"][name] for name in ("rust-units", "per-unit"))
    assert not any("continue-on-error" in step for step in WORKFLOW["jobs"]["per-unit"]["steps"])
