"""Required runtime manifest gate (PIPE-GATES-R017) against a fake cargo."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import required_runtime  # noqa: E402

# A fake cargo: `--list` prints the tests of the crate named after -p unless it
# is "empty"; a run fails for crate "broken".
FAKE_CARGO = """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
crate = args[args.index("-p") + 1]
if "--list" in args:
    if crate != "empty":
        print(f"{crate}::tests::one: test")
        print(f"{crate}::tests::two: test")
    sys.exit(0)
sys.exit(101 if crate == "broken" else 0)
"""


@pytest.fixture
def cargo(tmp_path: Path) -> str:
    path = tmp_path / "cargo"
    path.write_text(FAKE_CARGO, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def _manifest(tmp_path: Path, *crates: str) -> Path:
    path = tmp_path / "required-runtime.toml"
    path.write_text(
        "".join(f'[[entry]]\ncrate = "{c}"\nfilter = "tests::"\nfeatures = ["x"]\n' for c in crates), encoding="utf-8"
    )
    return path


# spec: PIPE-GATES-R017
def test_empty_selection_and_failed_test_block(tmp_path, cargo, capsys, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert required_runtime.main(["--manifest", str(_manifest(tmp_path, "empty")), "--cargo", cargo]) == 1
    assert "ZERO_SELECTED_TESTS" in capsys.readouterr().err
    assert required_runtime.main(["--manifest", str(_manifest(tmp_path, "broken")), "--cargo", cargo]) == 1
    assert "TEST_FAILED" in capsys.readouterr().err
    assert required_runtime.main(["--manifest", str(_manifest(tmp_path, "good", "other")), "--cargo", cargo]) == 0
    text = summary.read_text(encoding="utf-8")
    assert "`good::tests::one`" in text and "`other::tests::two`" in text


# spec: PIPE-GATES-R017
def test_malformed_manifest_refuses(tmp_path, cargo):
    path = tmp_path / "m.toml"
    path.write_text('[[entry]]\ncrate = "x"\n', encoding="utf-8")
    assert required_runtime.main(["--manifest", str(path), "--cargo", cargo]) == 2
