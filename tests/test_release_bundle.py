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
                   "implementation_name": "cpython", "platform_python_implementation": "CPython"}
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
    archive.write_bytes(b"exact source archive fixture")
    snapshot = {"schema": 2, **identity, "targets": proofs,
                "source": {"archive": {"file": archive.name, "sha256": guard.digest(archive)},
                           "rebuilt_wheel_proof": copy.deepcopy(proofs["linux-x86_64"])}}
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


def archive(path, name, *, link=False):
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
    archive(path, "fixture/pyproject.toml")
    project = source.extract(path, tmp_path / "extracted")
    assert source.build_requirements(guard, project) == ["maturin>=1"]


@pytest.mark.parametrize("name,link", [("../pyproject.toml", False), ("/pyproject.toml", False), ("fixture/link", True)])
def test_source_archive_rejects_escape_and_links(tmp_path, name, link):
    path = tmp_path / "fixture.tar.gz"
    archive(path, name, link=link)
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
