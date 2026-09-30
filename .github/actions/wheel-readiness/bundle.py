"""Verify every target's proof before a Maturin publication bundle is admitted.

No native target is substituted by the publisher's interpreter. The caller
supplies no target allowlist: the existing workflow matrix is the closed scope.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


def guard_module():
    spec = importlib.util.spec_from_file_location("wheel_bundle_guard", Path(__file__).with_name("readiness.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_producer(guard, proof: dict, target: str, identity: dict) -> None:
    guard.require(proof["schema"] == 1, "unsupported target receipt")
    guard.require(proof["target"] == target, "target receipt substituted")
    guard.require(proof["index"] == guard.PUBLIC_INDEX, "target receipt index changed")
    guard.require(proof["scope"] == "all-runtime-dependencies", "target receipt scope changed")
    for key, value in identity.items():
        guard.require(proof[key] == value, "target receipt source identity changed")
    guard.require(proof["interpreter"] == proof["context"]["interpreter"], "target interpreter substituted")
    guard.sibling("targets").validate(target, proof["context"])
    guard.require(bool(proof["wheels"]), "target receipt contains no wheels")


def validate_wheels(guard, directory: Path, proofs: dict, raw: str, identity: dict) -> dict:
    expected = guard.sibling("targets").TARGETS
    guard.require(set(proofs) == set(expected), "missing or unexpected target receipt")
    owned = {}
    packages = set()
    for target in expected:
        proof = proofs[target]
        validate_producer(guard, proof, target, identity)
        for item in proof["wheels"]:
            filename = item["file"]
            guard.require(Path(filename).name == filename and filename.endswith(".whl"), "invalid artifact name")
            guard.require(filename not in owned, "wheel has duplicate target ownership")
            path = directory / filename
            guard.require(path.is_file() and not path.is_symlink(), "target wheel is missing or linked")
            guard.verify_item(path, item, raw, proof["context"])
            packages.add((item["metadata"]["name"], item["metadata"]["version"]))
            owned[filename] = target
    guard.require(len(packages) == 1, "target package identity differs")
    return owned


def validate_source(guard, directory: Path, source: dict, proofs: dict, raw: str, identity: dict, evidence: Path) -> str:
    archive = source["archive"]
    name = archive["file"]
    guard.require(Path(name).name == name and name.endswith(".tar.gz"), "invalid source archive name")
    path = directory / name
    guard.require(path.is_file() and not path.is_symlink(), "source archive missing or linked")
    guard.require(guard.digest(path) == archive["sha256"], "source archive bytes changed")
    proof = source["rebuilt_wheel_proof"]
    validate_producer(guard, proof, "linux-x86_64", identity)
    guard.require(len(proof["wheels"]) == 1, "source proof must contain one rebuilt wheel")
    item = proof["wheels"][0]
    # Rebuilt bytes travel as a separate artifact, never inside the upload glob.
    guard.require(Path(item["file"]).name == item["file"], "invalid rebuilt wheel name")
    guard.require({path.name for path in evidence.iterdir()} == {item["file"]}, "source wheel evidence set changed")
    wheel = evidence / item["file"]
    guard.require(wheel.is_file() and not wheel.is_symlink(), "source wheel evidence missing or linked")
    guard.verify_item(wheel, item, raw, proof["context"])
    with tempfile.TemporaryDirectory(prefix="source-metadata-proof-") as temporary:
        source_checker = guard.sibling("source")
        project = source_checker.extract(path, Path(temporary))
        package = source_checker.package_identity(guard, project, name)
        requirements = source_checker.build_requirements(guard, project)
        guard.sibling("prerequisites").validate(
            guard, requirements, source["build_prerequisites"], proof["context"]
        )
    guard.require(package == (item["metadata"]["name"], item["metadata"]["version"]),
                  "source filename disagrees with rebuilt package identity")
    reference = proofs["linux-x86_64"]["wheels"][0]["metadata"]
    guard.require(item["metadata"] == reference, "source rebuilt runtime metadata differs from release wheel")
    return name


def verify_snapshot(directory: Path, snapshot: dict, raw: str, evidence: Path) -> None:
    guard = guard_module()
    guard.require(snapshot["schema"] == 2, "unsupported bundle proof")
    identity = guard.identity()
    for key, value in identity.items():
        guard.require(snapshot[key] == value, "bundle source identity changed")
    owned = validate_wheels(guard, directory, snapshot["targets"], raw, identity)
    source = validate_source(guard, directory, snapshot["source"], snapshot["targets"], raw, identity, evidence)
    actual = {path.name for path in directory.iterdir()}
    guard.require(actual == {*owned, source}, "publication bundle contains missing or extra artifacts")


def aggregate(directory: Path, receipts: Path, output: Path, raw: str, evidence: Path) -> None:
    guard = guard_module()
    output.unlink(missing_ok=True)
    expected = {*guard.sibling("targets").TARGETS, "sdist"}
    guard.require({path.name for path in receipts.iterdir()} == {name + ".json" for name in expected},
                  "target receipt directory is incomplete or contains unexpected files")
    proofs = {}
    for name in sorted(expected):
        path = receipts / (name + ".json")
        guard.require(path.is_file() and not path.is_symlink(), "receipt is not a regular file")
        proofs[name] = json.loads(path.read_text())
    source = proofs.pop("sdist")
    snapshot = {"schema": 2, **guard.identity(), "targets": proofs, "source": source}
    verify_snapshot(directory, snapshot, raw, evidence)
    output.write_text(json.dumps(snapshot, indent=2) + "\n")
