"""Nightly attached-source conformance gate (PIPE-GATES-R020) against fake docker and cargo."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import nightly_conformance  # noqa: E402

FAKE_DOCKER = """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
if args[0] == "run":
    ref = args[-1]
    if ref.startswith("never"):
        sys.exit(125)
    print("cid-" + ref.split("@")[0])
elif args[0] == "inspect":
    print("true ")
"""
# Conformance fails for the dialect named "bad" and for "drift".
FAKE_CARGO = """#!/usr/bin/env python3
import os, sys
sys.exit(1 if os.environ["CONFORMANCE_DIALECT"] in {"bad", "drift"} else 0)
"""
DIGEST = "sha256:" + "a" * 64


@pytest.fixture
def tools(tmp_path: Path) -> list[str]:
    paths = []
    for name, text in (("docker", FAKE_DOCKER), ("cargo", FAKE_CARGO)):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
        paths.append(str(path))
    return ["--docker", paths[0], "--cargo", paths[1]]


def _matrix(tmp_path: Path, dialects: list[str], deviations: str = "") -> Path:
    directory = tmp_path / "conformance"
    directory.mkdir(exist_ok=True)
    manifest = directory / "attached_matrix.toml"
    manifest.write_text(
        "".join(
            f'[[entry]]\ndialect = "{d}"\nimage = "{d}-image"\ndigest = "{DIGEST}"\nversion = "1"\n' for d in dialects
        ),
        encoding="utf-8",
    )
    (directory / "deviations.toml").write_text(deviations, encoding="utf-8")
    return manifest


UNREVIEWED = '[[deviation]]\ndialect = "drift"\nversion = "1"\nreason = "known rounding"\nreviewed_by = ""\n'
REVIEWED = UNREVIEWED.replace('reviewed_by = ""', 'reviewed_by = "maintainer"')


# spec: PIPE-GATES-R020
def test_failing_entry_and_unreviewed_difference_block(tmp_path, tools):
    assert nightly_conformance.main(["--manifest", str(_matrix(tmp_path, ["good", "bad"])), *tools]) == 1
    assert nightly_conformance.main(["--manifest", str(_matrix(tmp_path, ["drift"], UNREVIEWED)), *tools]) == 1
    assert nightly_conformance.main(["--manifest", str(_matrix(tmp_path, ["good", "drift"], REVIEWED)), *tools]) == 0


# spec: PIPE-GATES-R020
def test_image_that_does_not_start_and_bad_timeout_block(tmp_path, tools):
    assert nightly_conformance.main(["--manifest", str(_matrix(tmp_path, ["never"])), *tools]) == 1
    manifest = _matrix(tmp_path, ["good"])
    assert nightly_conformance.main(["--manifest", str(manifest), "--timeout-minutes", "61", *tools]) == 2
