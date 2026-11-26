"""Build gate for the root library and its lint profiles (PIPE-GATES-R021) against a fake cargo."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_gate  # noqa: E402

# A fake cargo: the first argument is the subcommand. `build` fails for a tree holding the file
# `compile-error`, `clippy` fails (as `-D warnings` does) for a tree holding `warning`, and a test
# run lists and passes the crate's tests.
FAKE_CARGO = """#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if args[0] == "build":
    sys.exit(101 if os.path.exists("compile-error") else 0)
if args[0] == "clippy":
    assert "--all-features" in args and "--all-targets" in args and args[-2:] == ["-D", "warnings"]
    sys.exit(101 if os.path.exists("warning") else 0)
if "--list" in args:
    print("scanner::tests::one: test")
sys.exit(0)
"""
MANIFEST = """[[clippy]]
name = "default"
args = ["--workspace"]

[[clippy]]
name = "catalog"
args = ["-p", "catalog"]

[[suite]]
crate = "scanner"
filter = "tests"
features = []
"""


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    cargo = tmp_path / "cargo"
    cargo.write_text(FAKE_CARGO, encoding="utf-8")
    cargo.chmod(0o755)
    manifest = tmp_path / "build-gate.toml"
    manifest.write_text(MANIFEST, encoding="utf-8")
    work = tmp_path / "crate"
    work.mkdir()
    monkeypatch.chdir(work)
    return str(cargo), manifest


# spec: PIPE-GATES-R021
def test_compile_error_and_clippy_warning_block(tree, capsys) -> None:
    cargo, manifest = tree
    assert build_gate.main(["--manifest", str(manifest), "--cargo", cargo]) == 0
    Path("compile-error").write_text("", encoding="utf-8")
    assert build_gate.main(["--manifest", str(manifest), "--cargo", cargo]) == 1
    assert "BUILD_GATE_FAILED: build:" in capsys.readouterr().err
    Path("compile-error").unlink()
    Path("warning").write_text("", encoding="utf-8")
    assert build_gate.main(["--manifest", str(manifest), "--cargo", cargo]) == 1
    err = capsys.readouterr().err
    assert "BUILD_GATE_FAILED: clippy default:" in err and "BUILD_GATE_FAILED: clippy catalog:" in err
    assert build_gate.main(["--manifest", str(manifest.with_name("absent.toml")), "--cargo", cargo]) == 2


# spec: PIPE-GATES-R021
def test_the_workflow_calls_the_gate_script_with_the_callers_manifest() -> None:
    document = yaml.safe_load((ROOT / ".github/workflows/build-gate.yml").read_text(encoding="utf-8"))
    assert document[True]["workflow_call"]["inputs"]["manifest"]["required"] is True
    steps = document["jobs"]["build-gate"]["steps"]
    assert any("scripts/build_gate.py" in step.get("run", "") for step in steps)
