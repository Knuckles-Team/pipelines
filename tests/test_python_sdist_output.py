"""The Python publisher builds, proves and uploads the sdist with the wheel (PIPE-RELEASE-R008)."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
PUBLISHER = ROOT / ".github/actions/publish-python-package/action.yml"
READINESS = ROOT / ".github/actions/wheel-readiness/action.yml"


def _steps() -> list[dict]:
    return yaml.safe_load(PUBLISHER.read_text())["runs"]["steps"]


def _step(name: str) -> dict:
    return next(step for step in _steps() if step.get("name") == name)


@pytest.mark.spec("PIPE-RELEASE-R008")
def test_sdist_is_built_proven_and_published_with_the_wheel() -> None:
    names = [step.get("name") for step in _steps()]
    order = [
        "Prove wheel runtime readiness",
        "Build source distribution",
        "Prove source distribution rebuild",
        "Upload Artifact",
        "Publish package",
    ]
    assert [names.index(name) for name in order] == sorted(names.index(n) for n in order)
    proof = _step("Prove source distribution rebuild")["with"]
    assert (proof["phase"], proof["directory"]) == ("source", "dist-sdist")
    assert "dist-sdist/*.tar.gz" in _step("Upload Artifact")["with"]["path"]
    publish = _step("Publish package")["run"]
    upload = next(line for line in publish.splitlines() if "twine upload" in line)
    assert "dist/*.whl" in upload and "dist-sdist/*.tar.gz" in upload
    # A re-run for an existing release adds only the missing file.
    assert "--skip-existing" in upload
    assert '-"$BUILD_VERSION".tar.gz' in publish


@pytest.mark.spec("PIPE-RELEASE-R008")
def test_readiness_action_proves_the_named_directory() -> None:
    action = yaml.safe_load(READINESS.read_text())
    assert action["inputs"]["directory"]["default"] == "dist"
    run = next(step["run"] for step in action["runs"]["steps"] if "readiness.py" in str(step.get("run")))
    assert '--directory "$READINESS_DIRECTORY"' in run


@pytest.mark.spec("PIPE-RELEASE-R008")
def test_sdist_build_line_produces_one_versioned_archive(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=84"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "release-output-fixture"\nversion = "1.0.0"\n'
        '[tool.setuptools]\npy-modules = ["fixture_module"]\n'
    )
    (tmp_path / "fixture_module.py").write_text("VALUE = 1\n")
    line = next(
        raw.strip()
        for raw in _step("Build source distribution")["run"].splitlines()
        if raw.strip().startswith("uv build ")
    )
    uv = shutil.which("uv")
    assert uv, "the publisher's uv build tool must be available"
    command = [uv, *shlex.split(line)[1:], "--offline", "--no-build-isolation", "--python", sys.executable]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    archives = sorted(p.name for p in (tmp_path / "dist-sdist").iterdir())
    assert archives == ["release_output_fixture-1.0.0.tar.gz"]
    assert not (tmp_path / "dist").exists()


MATURIN = ROOT / ".github/workflows/maturin_pipeline.yml"
READINESS_DOC = ROOT / "reference/python-release-readiness.md"


@pytest.mark.spec("PIPE-RELEASE-R008")
def test_maturin_sdist_covers_the_package_its_wheels_publish() -> None:
    jobs = yaml.safe_load(MATURIN.read_text())["jobs"]
    # One package per caller: no job may point maturin at another project.
    for name, job in jobs.items():
        for step in job.get("steps", []):
            args = str((step.get("with") or {}).get("args", ""))
            assert "--manifest-path" not in args and "-m " not in args, name
            assert "working-directory" not in step, name
    sdist = next(step for step in jobs["sdist"]["steps"] if step.get("name") == "Build sdist")
    assert sdist["with"]["command"] == "sdist" and "--out dist" in sdist["with"]["args"]
    proof = next(step for step in jobs["sdist"]["steps"] if step.get("name") == "Prove exact source archive rebuild")
    assert proof["with"]["phase"] == "source"
    upload = next(step for step in jobs["sdist"]["steps"] if step.get("name") == "Verify source and upload artifact")
    assert upload["with"]["artifact-name"].startswith("wheels-")
    publish = jobs["publish"]
    assert "sdist" in publish["needs"]
    download = next(step for step in publish["steps"] if step.get("with", {}).get("pattern") == "wheels-*")
    assert download["with"]["path"] == "dist"
    pypi = next(step for step in publish["steps"] if step.get("name") == "Publish to PyPI")
    assert pypi["with"]["packages-dir"] == "dist/"


@pytest.mark.spec("PIPE-RELEASE-R008")
def test_readiness_doc_states_the_wheel_availability_rule() -> None:
    text = " ".join(READINESS_DOC.read_text().split())
    assert "builds/uploads wheels only" not in text
    assert "--only-binary :all:" in text and "allow-source-build" in text
    assert "compatible with the target interpreter or platform" in text
    assert "`sdist_missing`" in text and "not a failure" in text
    assert "only an sdist" in text and "no compatible wheel, fails readiness" in text
    assert "`partial_publish` only while the forge reports the release run as in progress" in text
    assert "never replaces a checked wheel at install time" in text
