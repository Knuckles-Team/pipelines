"""Synthetic target and exact-source receipts; no native builds or network."""
from __future__ import annotations

import copy
import io
import json
import tarfile
from pathlib import Path

import pytest

from tests.test_wheel_readiness import guard, report, wheel

bundle = guard.sibling("bundle")
source = guard.sibling("source")

TARGETS = {
    "linux-x86_64": ("linux", "x86_64", "manylinux_2_28_x86_64"),
    "linux-aarch64": ("linux", "aarch64", "manylinux_2_28_aarch64"),
    "macos-aarch64": ("darwin", "arm64", "macosx_11_0_arm64"),
    "windows-x86_64": ("win32", "AMD64", "win_amd64"),
}


def context(target):
    system, machine, tag = TARGETS[target]
    environment = {**guard.default_environment(), "sys_platform": system, "platform_machine": machine,
                   "python_full_version": "3.13.1", "python_version": "3.13",
                   "implementation_name": "cpython", "platform_python_implementation": "CPython",
                   "implementation_version": "3.13.1", "os_name": "nt" if system == "win32" else "posix",
                   "platform_system": {"linux": "Linux", "darwin": "Darwin", "win32": "Windows"}[system]}
    interpreter = {"platform": system, "machine": machine, "version": "3.13.1", "implementation": "CPython"}
    return {"environment": environment, "interpreter": interpreter, "tags": ["cp313-cp313-" + tag]}


@pytest.fixture
def release_bundle(tmp_path, monkeypatch):
    directory = tmp_path / "dist"
    directory.mkdir()
    evidence = tmp_path / "source-evidence"
    evidence.mkdir()
    identity = {"source_commit": "a" * 40, "contract_commit": "b" * 40}
    monkeypatch.setattr(guard, "identity", lambda: identity)
    monkeypatch.setattr(bundle, "guard_module", lambda: guard)
    proofs = {}
    for target, (_, _, tag) in TARGETS.items():
        observed = context(target)
        path = wheel(directory, name="fixture-1.0-cp313-cp313-" + tag + ".whl")
        metadata = guard.metadata(path, observed)
        resolver = report(path, metadata)
        resolver["environment"] = observed["environment"]
        item = {"file": path.name, "sha256": guard.digest(path), "metadata": metadata,
                "profiles": ["base"], "evidence": [{"profile": "base", "report": resolver}]}
        proofs[target] = {"schema": 1, "target": target, "index": guard.PUBLIC_INDEX,
                          "scope": "all-runtime-dependencies", **identity, "context": observed,
                          "interpreter": observed["interpreter"], "wheels": [item]}
    reference = directory / proofs["linux-x86_64"]["wheels"][0]["file"]
    (evidence / reference.name).write_bytes(reference.read_bytes())
    archive = directory / "fixture-1.0.tar.gz"
    write_archive(archive, "fixture/pyproject.toml")
    snapshot = {"schema": 2, **identity, "targets": proofs,
                "source": {"archive": {"file": archive.name, "sha256": guard.digest(archive)},
                           "rebuilt_wheel_proof": copy.deepcopy(proofs["linux-x86_64"]),
                           "build_prerequisites": {
                               "version": "1", "pip_version": "25.1.1",
                               "environment": context("linux-x86_64")["environment"],
                               "install": [{"metadata": {"name": "maturin", "version": "1"},
                                            "download_info": {"url": "https://files.pythonhosted.org/maturin-1-py3-none-any.whl",
                                                              "archive_info": {"hashes": {"sha256": "c" * 64}}}}],
                           }}}
    return directory, evidence, snapshot


def test_complete_native_bundle_accepts_all_target_contexts(release_bundle):
    directory, evidence, snapshot = release_bundle
    bundle.verify_snapshot(directory, snapshot, '["base"]', evidence)


@pytest.mark.parametrize("change", ["missing", "duplicate", "target", "commit", "profile", "version", "resolver", "marker", "bytes", "extra", "sdist", "source-wheel"])
def test_bundle_rejects_incomplete_or_substituted_proof(release_bundle, change):
    directory, evidence, snapshot = release_bundle
    proof = snapshot["targets"]["linux-aarch64"]
    item = proof["wheels"][0]
    if change == "missing":
        del snapshot["targets"]["linux-aarch64"]
    elif change == "duplicate":
        proof["wheels"] *= 2
    elif change == "target":
        proof["target"] = "linux-x86_64"
    elif change == "commit":
        proof["source_commit"] = "c" * 40
    elif change == "profile":
        item["profiles"] = []
    elif change == "version":
        item["metadata"]["version"] = "2.0"
    elif change == "resolver":
        item["evidence"][0]["report"]["pip_version"] = "25.2"
    elif change == "marker":
        proof["context"]["environment"]["platform_machine"] = "x86_64"
    elif change == "bytes":
        (directory / item["file"]).write_bytes(b"changed")
    elif change == "extra":
        (directory / "extra.whl").write_bytes(b"extra")
    elif change == "sdist":
        (directory / snapshot["source"]["archive"]["file"]).write_bytes(b"changed")
    elif change == "source-wheel":
        next(evidence.iterdir()).write_bytes(b"changed")
    with pytest.raises(ValueError):
        bundle.verify_snapshot(directory, snapshot, '["base"]', evidence)


def test_missing_target_receipt_removes_stale_success(release_bundle, tmp_path):
    directory, evidence, snapshot = release_bundle
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    output = tmp_path / "proof.json"
    output.write_text(json.dumps(snapshot))
    with pytest.raises(ValueError, match="incomplete"):
        bundle.aggregate(directory, receipts, output, '["base"]', evidence)
    assert not output.exists()


def write_archive(path, name, *, link=False):
    with tarfile.open(path, "w:gz") as tar:
        entry = tarfile.TarInfo(name)
        if link:
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/tmp/outside"
            tar.addfile(entry)
        else:
            payload = b'[build-system]\nrequires=["maturin>=1"]\n'
            entry.size = len(payload)
            tar.addfile(entry, io.BytesIO(payload))


def test_source_archive_extracts_only_one_bounded_project(tmp_path):
    path = tmp_path / "fixture.tar.gz"
    write_archive(path, "fixture/pyproject.toml")
    project = source.extract(path, tmp_path / "extracted")
    assert source.build_requirements(guard, project) == ["maturin>=1"]


@pytest.mark.parametrize("name,link", [("../pyproject.toml", False), ("/pyproject.toml", False), ("fixture/link", True)])
def test_source_archive_rejects_escape_and_links(tmp_path, name, link):
    path = tmp_path / "fixture.tar.gz"
    write_archive(path, name, link=link)
    with pytest.raises(ValueError):
        source.extract(path, tmp_path / "extracted")


def test_bootstrap_rejects_changed_pinned_resolver_bytes(tmp_path):
    bootstrap = guard.sibling("bootstrap")
    path = tmp_path / bootstrap.PIN["filename"]
    path.write_bytes(b"substitution")
    with pytest.raises(ValueError, match="reviewed pin"):
        bootstrap.verify_pin(path)


def test_native_target_cannot_be_proved_by_cross_build_host():
    with pytest.raises(ValueError, match="declared target"):
        guard.sibling("targets").validate("linux-aarch64", context("linux-x86_64"))


@pytest.mark.parametrize("field,value", [("pip_version", "26.0"), ("environment", {}), ("install", [])])
def test_source_prerequisite_receipt_cannot_be_omitted_or_replaced(release_bundle, field, value):
    directory, evidence, snapshot = release_bundle
    snapshot["source"]["build_prerequisites"][field] = value
    with pytest.raises(ValueError):
        bundle.verify_snapshot(directory, snapshot, '["base"]', evidence)


def test_source_prerequisite_report_must_prove_archive_constraint(release_bundle):
    directory, evidence, snapshot = release_bundle
    item = snapshot["source"]["build_prerequisites"]["install"][0]
    item["metadata"]["version"] = "0.1"
    with pytest.raises(ValueError, match="version mismatch"):
        bundle.verify_snapshot(directory, snapshot, '["base"]', evidence)


def test_source_rebuild_runs_a_real_dependency_free_python_backend(tmp_path, monkeypatch):
    """Exercise pip's build path, without seeding an env or compiling native code."""
    import sys
    from types import SimpleNamespace

    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires=[]\nbuild-backend="fixture_backend"\nbackend-path=["."]\n'
    )
    (project / "fixture_backend.py").write_text(
        'from pathlib import Path\nimport zipfile\n'
        'def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):\n'
        '    name = "fixture-1.0-py3-none-any.whl"\n'
        '    with zipfile.ZipFile(Path(wheel_directory) / name, "w") as archive:\n'
        '        archive.writestr("fixture-1.0.dist-info/METADATA", '
        '"Metadata-Version: 2.3\\nName: fixture\\nVersion: 1.0\\n")\n'
        '        archive.writestr("fixture-1.0.dist-info/WHEEL", '
        '"Wheel-Version: 1.0\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n")\n'
        '        archive.writestr("fixture-1.0.dist-info/RECORD", "")\n'
        '    return name\n'
    )
    original = guard.sibling
    bootstrap = original("bootstrap")
    fixture_bootstrap = SimpleNamespace(PIN=bootstrap.PIN, environment=bootstrap.environment,
                                       create=lambda *_: Path(sys.executable))
    monkeypatch.setattr(guard, "sibling", lambda name: fixture_bootstrap if name == "bootstrap" else original(name))
    candidate, prerequisites = source.rebuild(guard, project, tmp_path)
    assert guard.metadata(candidate)["version"] == "1.0"
    assert prerequisites is None


def test_source_archive_rejects_duplicate_normalized_paths(tmp_path):
    path = tmp_path / "fixture.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name in ("fixture/pyproject.toml", "fixture/./pyproject.toml"):
            member = tarfile.TarInfo(name)
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="duplicate"):
        source.extract(path, tmp_path / "extracted")


def test_source_build_prerequisite_transitive_extra_cannot_be_omitted(release_bundle):
    directory, evidence, snapshot = release_bundle
    item = snapshot["source"]["build_prerequisites"]["install"][0]
    item["metadata"]["requires_dist"] = ["missing[base]>=1"]
    with pytest.raises(ValueError, match="missing transitive"):
        bundle.verify_snapshot(directory, snapshot, '["base"]', evidence)


def test_producers_and_publishers_require_the_closed_target_matrix():
    import yaml
    from tests.test_wheel_readiness import ROOT

    workflow = yaml.safe_load((ROOT / ".github/workflows/maturin_pipeline.yml").read_text())
    for job in ("linux", "macos", "windows"):
        producer = next(step for step in workflow["jobs"][job]["steps"]
                        if step.get("uses", "").endswith("/maturin-build-wheels"))
        assert producer["with"]["runtime-profiles"] == "${{ inputs.runtime-profiles }}"
        assert "readiness-target" in producer["with"]
    native = yaml.safe_load((ROOT / ".github/actions/maturin-build-wheels/action.yml").read_text())
    names = [step["name"] for step in native["runs"]["steps"]]
    assert names.index("Build wheels") < names.index("Prove native wheel readiness") < names.index("Verify source and upload artifact")
    steps = workflow["jobs"]["sdist"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Build sdist") < names.index("Prove exact source archive rebuild") < names.index("Verify source and upload artifact")
    source_proof = next(step for step in steps if step.get("name") == "Prove exact source archive rebuild")
    assert source_proof["with"]["phase"] == "source"
    publish = workflow["jobs"]["publish"]
    assert set(publish["needs"]) == {"linux", "macos", "windows", "sdist"}
    aggregate = next(step for step in publish["steps"] if step.get("name") == "Prove wheel runtime readiness")
    assert aggregate["with"]["phase"] == "aggregate"
    assert not any(step.get("continue-on-error") or step.get("if") for step in publish["steps"])
    verifier = next(step for step in publish["steps"] if step.get("name") == "Reverify exact upload bytes")
    assert '--release-version "$BUILD_VERSION"' in verifier["run"]


@pytest.mark.parametrize("field,value", [("os_name", "posix"), ("platform_system", "Linux"),
                                        ("implementation_version", "3.12.0")])
def test_native_windows_receipt_rejects_host_marker_substitution(field, value):
    observed = context("windows-x86_64")
    observed["environment"][field] = value
    with pytest.raises(ValueError, match="marker environment"):
        guard.sibling("targets").validate("windows-x86_64", observed)


@pytest.mark.parametrize("tag", ["cp313-cp313-manylinux_2_28_x86_64", "cp314-cp314-win_amd64",
                                 "cp312-cp312-win_amd64", "cp313-cp313-any"])
def test_native_windows_receipt_rejects_foreign_platform_or_interpreter_tags(tag):
    observed = context("windows-x86_64")
    observed["tags"] = [tag]
    with pytest.raises(ValueError):
        guard.sibling("targets").validate("windows-x86_64", observed)


def test_native_cp313_accepts_older_stable_abi_wheels():
    observed = context("linux-aarch64")
    observed["tags"] = ["cp311-abi3-manylinux_2_28_aarch64", "py3-none-any"]
    guard.sibling("targets").validate("linux-aarch64", observed)


def test_source_rebuild_must_preserve_python_range(release_bundle):
    directory, evidence, snapshot = release_bundle
    proof = snapshot["source"]["rebuilt_wheel_proof"]
    item = proof["wheels"][0]
    rebuilt = wheel(evidence, name=item["file"], python=">=3.13")
    item["sha256"] = guard.digest(rebuilt)
    item["metadata"] = guard.metadata(rebuilt, proof["context"])
    resolver = report(rebuilt, item["metadata"])
    resolver["environment"] = proof["context"]["environment"]
    item["evidence"] = [{"profile": "base", "report": resolver}]
    with pytest.raises(ValueError, match="source rebuilt runtime metadata differs"):
        bundle.verify_snapshot(directory, snapshot, '["base"]', evidence)
