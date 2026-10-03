"""Source provenance and same-version counterfeit rejection for jscpd."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from pipelines_hooks.core import jscpd_build as build
from pipelines_hooks.core.errors import CannotRun

REPO = Path(__file__).resolve().parents[2]


def receipt(executable: Path) -> dict:
    data = {
        "identity": build.build_identity(),
        "compiler": "rustc 1.97.0 (fixture)",
        "binary_sha256": build.sha256(executable),
    }
    executable.with_suffix(".provenance.json").write_text(json.dumps(data))
    return data


@pytest.fixture
def executable(tmp_path):
    target = tmp_path / "jscpd"
    target.write_text("#!/bin/sh\necho 'cpd 5.0.16'\n")
    target.chmod(0o755)
    receipt(target)
    return target


def test_receipt_accepts_exact_identity(executable):
    assert build.verify_receipt(executable)["identity"] == build.build_identity()


@pytest.mark.parametrize(
    "field",
    ["source_commit", "patch_sha256", "lock_sha256", "rust_toolchain", "architecture"],
)
def test_receipt_rejects_input_drift(executable, field):
    data = receipt(executable)
    data["identity"][field] = "wrong"
    executable.with_suffix(".provenance.json").write_text(json.dumps(data))
    with pytest.raises(CannotRun, match="identity mismatch"):
        build.verify_receipt(executable)


def test_receipt_rejects_changed_binary(executable):
    executable.write_bytes(b"different binary with same version string")
    with pytest.raises(CannotRun, match="checksum"):
        build.verify_receipt(executable)


def test_receipt_rejects_missing_provenance(executable):
    executable.with_suffix(".provenance.json").unlink()
    with pytest.raises(CannotRun, match="provenance"):
        build.verify_receipt(executable)


@pytest.mark.parametrize(
    "negative,positive",
    [([{"format": "markdown"}], [{"format": "markdown"}]), ([], [])],
)
def test_probe_rejects_false_positive_or_lost_true_clone(
    executable, monkeypatch, negative, positive
):
    outputs = iter([negative, positive])
    monkeypatch.setattr(build, "_scan", lambda *args: next(outputs))
    with pytest.raises(CannotRun, match="contract failed"):
        build.require_corrected_build(str(executable))


def test_probe_requires_both_controls(executable, monkeypatch):
    outputs = iter([[], [{"format": "markdown"}]])
    monkeypatch.setattr(build, "_scan", lambda *args: next(outputs))
    build.require_corrected_build(str(executable))


def test_cache_identity_changes_with_patch(monkeypatch):
    before = build.cache_key()
    monkeypatch.setattr(build, "PATCH_SHA256", "different")
    assert build.cache_key() != before


def test_installer_embeds_reviewed_patch_and_workflow_keys_all_inputs():
    assert (
        build.sha256(REPO / "scripts/patches/jscpd-markdown-glob.patch")
        == build.PATCH_SHA256
    )
    workflow = (REPO / ".github/workflows/ci.yml").read_text()
    for path in (
        "scripts/install_jscpd.py",
        "scripts/patches/jscpd-markdown-glob.patch",
        "pipelines_hooks/core/jscpd_build.py",
    ):
        assert path in workflow
    assert build.RUST_TOOLCHAIN == "1.97.0"
    assert (
        f"rustup toolchain install {build.RUST_TOOLCHAIN} --profile minimal" in workflow
    )
    assert "runner.arch" in workflow


def test_provisioner_hash_check_fails_before_extraction(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "install_jscpd_under_test", REPO / "scripts/install_jscpd.py"
    )
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    archive = tmp_path / "untrusted.tar.gz"
    archive.write_bytes(b"not an archive")
    with pytest.raises(ValueError, match="checksum mismatch"):
        installer.prepare_source(
            archive,
            REPO / "scripts/patches/jscpd-markdown-glob.patch",
            tmp_path / "extract",
        )
    assert not (tmp_path / "extract").exists()


def test_cached_installer_reverifies_before_reuse(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "cached_install_jscpd", REPO / "scripts/install_jscpd.py"
    )
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    executable = tmp_path / build.cache_key() / "bin/jscpd"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"upstream binary without receipt")
    monkeypatch.setattr(
        installer, "run", lambda *a, **kw: pytest.fail("must not build or fall back")
    )
    with pytest.raises(CannotRun, match="provenance"):
        installer.install(tmp_path)


def test_non_mapping_receipt_is_rejected(executable):
    executable.with_suffix(".provenance.json").write_text("[]")
    with pytest.raises(CannotRun, match="provenance"):
        build.verify_receipt(executable)


def test_other_scanner_build_probe_remains_registered():
    from pipelines_hooks.core import tools
    from pipelines_hooks.core.kiss_fork import require_fork_build

    assert tools._BUILD_PROBES["kiss"] is require_fork_build
    assert tools._BUILD_PROBES["jscpd"] is build.require_corrected_build


@pytest.mark.parametrize(
    "compiler", ["rustc 1.97.1 (fixture)", "rustc 1.98.0 (fixture)"]
)
def test_receipt_rejects_other_compiler_patch_versions(executable, compiler):
    data = receipt(executable)
    data["compiler"] = compiler
    executable.with_suffix(".provenance.json").write_text(json.dumps(data))
    with pytest.raises(CannotRun, match="compiler identity mismatch"):
        build.verify_receipt(executable)
