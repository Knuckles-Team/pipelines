"""The Python publisher produces exactly the files the wheel guard accepts."""

from __future__ import annotations

import importlib.util
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
PUBLISHER = ROOT / ".github/actions/publish-python-package/action.yml"
CHECKER = ROOT / ".github/actions/wheel-readiness/readiness.py"


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("wheel_output_guard", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory):
    root = tmp_path_factory.mktemp("publisher-wheel")
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=84"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "release-output-fixture"\nversion = "1.0.0"\n'
        '[tool.setuptools]\npy-modules = ["fixture_module"]\n'
    )
    (root / "fixture_module.py").write_text("VALUE = 1\n")
    action = yaml.safe_load(PUBLISHER.read_text())
    step = next(item for item in action["runs"]["steps"] if item["name"] == "Build package")
    commands = [shlex.split(line.strip()) for line in step["run"].splitlines()
                if line.strip().startswith("uv build ")]
    assert len(commands) == 1
    uv = shutil.which("uv")
    assert uv, "the publisher's uv build tool must be available"
    command = [uv, *commands[0][1:], "--offline", "--no-build-isolation", "--python", sys.executable]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return root / "dist"


def test_publisher_build_output_passes_exact_wheel_guard(built_wheel, guard):
    """PIPE-RELEASE-R003: execute the real publication build line without downloads."""
    wheels = guard.wheel_set(built_wheel)
    assert len(wheels) == 1
    assert not (built_wheel / ".gitignore").exists()
    assert guard.metadata(wheels[0])["name"] == "release-output-fixture"


@pytest.mark.parametrize("unexpected", [".gitignore", "notes.txt", "fixture.tar.gz"])
def test_extra_artifact_still_blocks_release(built_wheel, guard, tmp_path, *, unexpected):
    """The build fix must never relax the publication artifact boundary."""
    source = next(built_wheel.glob("*.whl"))
    shutil.copyfile(source, tmp_path / source.name)
    (tmp_path / unexpected).write_bytes(b"unproven")
    with pytest.raises(ValueError, match="only regular wheels"):
        guard.wheel_set(tmp_path)


def test_symlinked_wheel_still_blocks_release(built_wheel, guard, tmp_path):
    source = next(built_wheel.glob("*.whl"))
    (tmp_path / source.name).symlink_to(source)
    with pytest.raises(ValueError, match="only regular wheels"):
        guard.wheel_set(tmp_path)
