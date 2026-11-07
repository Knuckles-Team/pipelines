"""PIPE-RELEASE-R002: the early guard binds tag, package version, bumpversion and PyPI before any build."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
ACTION = ROOT / ".github/actions/verify-release-version"
REFERENCE = "./.pipeline-contract/.github/actions/verify-release-version"
SETUP_UV = "astral-sh/setup-uv@bec219d24cd3e171d82865faccec33120bb574f4"


@pytest.fixture
def guard():
    spec = importlib.util.spec_from_file_location("release_version_guard", ACTION / "verify_release_version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def package(tmp_path, version="0.5.1", bump=None):
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "Demo_Pkg"\nversion = "{version}"\n')
    if bump:
        (tmp_path / ".bumpversion.cfg").write_text(f"[bumpversion]\ncurrent_version = {bump}\n")
    return tmp_path


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_published_wheel_guard_sets_up_pinned_uv_before_publisher() -> None:
    action = yaml.safe_load((ACTION / "action.yml").read_text())
    steps = action["runs"]["steps"]
    setup = next(step for step in steps if step.get("name") == "Set up uv for published wheel verification")
    publisher = next(step for step in steps if step.get("name") == "Verify published wheel payload and container pin")

    assert setup == {
        "name": "Set up uv for published wheel verification",
        "if": "inputs.mode == 'published-wheel'",
        "uses": SETUP_UV,
    }
    assert publisher["if"] == "inputs.mode == 'published-wheel'"
    assert "public_wheel.py" in publisher["run"]
    assert steps.index(setup) < steps.index(publisher)


def absent(name, version, base):
    return False


def present(name, version, base):
    return True


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_matching_tag_passes(guard, tmp_path):
    assert guard.verify(package(tmp_path, bump="0.5.1"), "refs/tags/v0.5.1", lookup=absent) == "0.5.1"


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_stale_version_under_new_tag_is_refused(guard, tmp_path):
    with pytest.raises(guard.GuardError, match="tag v0.5.1 does not match package version 0.5.0"):
        guard.verify(package(tmp_path, "0.5.0"), "refs/tags/v0.5.1", lookup=absent)


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_version_already_on_pypi_is_refused(guard, tmp_path):
    with pytest.raises(guard.GuardError, match="already on PyPI"):
        guard.verify(package(tmp_path), "refs/tags/v0.5.1", lookup=present)


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_bumpversion_disagreement_is_refused(guard, tmp_path):
    with pytest.raises(guard.GuardError, match="current_version 0.5.0 differs"):
        guard.verify(package(tmp_path, bump="0.5.0"), "refs/tags/v0.5.1", lookup=absent)


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_config_dir_bumpversion_is_read(guard, tmp_path):
    package(tmp_path)
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config/bumpversion.cfg").write_text("[bumpversion]\ncurrent_version = 0.4.9\n")
    with pytest.raises(guard.GuardError, match=r"\.config/bumpversion\.cfg"):
        guard.verify(tmp_path, "refs/tags/v0.5.1", lookup=absent)


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_non_tag_ref_still_checks_pypi(guard, tmp_path):
    assert guard.verify(package(tmp_path), "refs/heads/main", lookup=absent) == "0.5.1"
    with pytest.raises(guard.GuardError, match="already on PyPI"):
        guard.verify(package(tmp_path), "refs/heads/main", lookup=present)


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_maturin_dynamic_version_reads_the_manifest(guard, tmp_path):
    (tmp_path / "crates/py").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "eg"\ndynamic = ["version"]\n[tool.maturin]\nmanifest-path = "crates/py/Cargo.toml"\n'
    )
    (tmp_path / "crates/py/Cargo.toml").write_text('[package]\nname = "py"\nversion = "2.27.6"\n')
    assert guard.verify(tmp_path, "refs/tags/v2.27.6", lookup=absent) == "2.27.6"
    with pytest.raises(guard.GuardError, match="does not match package version 2.27.6"):
        guard.verify(tmp_path, "refs/tags/v2.27.7", lookup=absent)


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_unresolvable_version_is_refused(guard, tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    with pytest.raises(guard.GuardError, match="neither a static nor a dynamic"):
        guard.verify(tmp_path, "refs/tags/v1.0.0", lookup=absent)


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_pypi_outage_fails_closed(guard, monkeypatch):
    def boom(*args, **kwargs):
        raise guard.URLError("down")

    class Opener:
        open = staticmethod(boom)

    monkeypatch.setattr(guard, "build_opener", lambda *a: Opener)
    with pytest.raises(guard.GuardError, match="refusing to release unverified"):
        guard.pypi_has_version("demo", "1.0.0")


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_main_reports_mismatch(guard, tmp_path, capsys):
    package(tmp_path, "0.5.0")
    code = guard.main(["--root", str(tmp_path), "--ref", "refs/tags/v0.5.1", "--pypi", "https://127.0.0.1:9"])
    assert code == 1
    assert "does not match package version 0.5.0" in capsys.readouterr().err


@pytest.mark.spec("PIPE-RELEASE-R002")
def test_every_shared_release_path_runs_the_guard_before_building():
    python = yaml.safe_load((ROOT / ".github/workflows/python_pipeline.yml").read_text())
    steps = python["jobs"]["publish-pypi"]["steps"]
    guard_at = next(i for i, s in enumerate(steps) if s.get("uses") == REFERENCE)
    build_at = next(i for i, s in enumerate(steps) if s.get("name") == "Build, publish and release")
    contract_at = next(i for i, s in enumerate(steps) if s.get("name") == "Checkout pipeline contract")
    assert contract_at < guard_at < build_at
    native = yaml.safe_load((ROOT / ".github/workflows/maturin_pipeline.yml").read_text())["jobs"]
    assert any(s.get("uses") == REFERENCE for s in native["version-guard"]["steps"])
    for job in ("linux", "macos", "windows", "sdist"):
        assert "version-guard" in native[job]["needs"]
    action = yaml.safe_load((ACTION / "action.yml").read_text())
    assert "verify_release_version.py" in action["runs"]["steps"][0]["run"]


def uploaded_at(stamp):
    def lookup(name, version, base):
        return stamp

    return lookup


@pytest.mark.spec("PIPE-RELEASE-R029.3")
def test_a_tag_published_after_its_commit_is_a_local_release(guard, tmp_path):
    root = package(tmp_path, bump="0.5.1")
    with pytest.raises(guard.AlreadyPublished, match="attested local build"):
        guard.verify(
            root,
            "refs/tags/v0.5.1",
            lookup=uploaded_at("2026-11-07T12:05:00.000000Z"),
            committed="2026-11-07T12:00:00+00:00",
        )


@pytest.mark.spec("PIPE-RELEASE-R029.3")
def test_a_version_published_before_the_commit_is_still_a_stale_tag(guard, tmp_path):
    root = package(tmp_path)
    late_commit = "2026-11-08T09:00:00+00:00"
    with pytest.raises(guard.GuardError, match="already on PyPI") as caught:
        guard.verify(root, "refs/tags/v0.5.1", lookup=uploaded_at("2026-11-07T12:05:00Z"), committed=late_commit)
    assert not isinstance(caught.value, guard.AlreadyPublished)
    # A branch ref or an unknown commit time never counts as a local release.
    with pytest.raises(guard.GuardError, match="already on PyPI"):
        guard.verify(root, "refs/heads/main", lookup=uploaded_at("2026-11-09T00:00:00Z"), committed=late_commit)
    with pytest.raises(guard.GuardError, match="already on PyPI"):
        guard.verify(root, "refs/tags/v0.5.1", lookup=present, committed=late_commit)


@pytest.mark.spec("PIPE-RELEASE-R029.3")
def test_main_writes_published_for_a_local_release(guard, tmp_path, monkeypatch, capsys):
    package(tmp_path, bump="0.5.1")
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(guard, "commit_time", lambda root: "2026-11-07T12:00:00+00:00")
    monkeypatch.setattr(guard, "pypi_has_version", uploaded_at("2026-11-07T12:01:00Z"))
    assert guard.main(["--root", str(tmp_path), "--ref", "refs/tags/v0.5.1"]) == 0
    assert output.read_text() == "published=true\n"
    assert "Release already published" in capsys.readouterr().out
    monkeypatch.setattr(guard, "pypi_has_version", absent)
    output.unlink()
    assert guard.main(["--root", str(tmp_path), "--ref", "refs/tags/v0.5.1"]) == 0
    assert output.read_text() == "published=false\n"


@pytest.mark.spec("PIPE-RELEASE-R029.3")
def test_hosted_release_skips_the_upload_of_a_locally_published_version():
    python = yaml.safe_load((ROOT / ".github/workflows/python_pipeline.yml").read_text())
    steps = python["jobs"]["publish-pypi"]["steps"]
    guard_at = next(i for i, s in enumerate(steps) if s.get("uses") == REFERENCE)
    assert steps[guard_at]["id"] == "version"
    for step in steps[guard_at + 1 :]:
        assert step["if"].startswith("steps.version.outputs.published != 'true'"), step["name"]
    action = yaml.safe_load((ACTION / "action.yml").read_text())
    assert action["outputs"]["published"]["value"] == "${{ steps.unpublished.outputs.published }}"
    publish = (ROOT / ".github/actions/publish-python-package/action.yml").read_text()
    assert (
        "twine upload --config-file /dev/null --repository-url https://upload.pypi.org/legacy/ --skip-existing"
        in publish
    )
    native = yaml.safe_load((ROOT / ".github/workflows/maturin_pipeline.yml").read_text())["jobs"]
    assert native["version-guard"]["outputs"]["published"] == "${{ steps.version.outputs.published }}"
    upload = next(s for s in native["publish"]["steps"] if s.get("name") == "Publish to PyPI")
    assert upload["with"]["skip-existing"] is True
    # The hosted-only platform wheels still build after a local Linux release.
    for job in ("macos", "windows"):
        assert "if" not in native[job]
