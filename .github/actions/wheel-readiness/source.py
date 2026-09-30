"""Bind an exact sdist to a wheel rebuilt in an isolated public-dependency env."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib


def extract(archive: Path, directory: Path) -> Path:
    """Reject links, escapes, duplicates, special files and unbounded archives."""
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        if not members or len(members) > 100000 or sum(item.size for item in members) > 256 * 1024 * 1024:
            raise ValueError("source archive exceeds the bounded proof scope")
        names = set()
        roots = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name or not path.parts:
                raise ValueError("source archive path escapes its root")
            if member.name in names or not (member.isfile() or member.isdir()):
                raise ValueError("source archive has duplicate, linked or special entries")
            names.add(member.name)
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError("source archive must have exactly one project root")
        source.extractall(directory, members=members, filter="data")
    project = directory / roots.pop()
    if not (project / "pyproject.toml").is_file():
        raise ValueError("source archive lacks pyproject.toml")
    return project


def build_requirements(guard, project: Path) -> list[str]:
    data = tomllib.loads((project / "pyproject.toml").read_text())
    requirements = data["build-system"]["requires"]
    guard.require(isinstance(requirements, list) and bool(requirements), "source build prerequisites missing")
    for raw in requirements:
        guard.require(isinstance(raw, str) and guard.Requirement(raw).url is None,
                      "source build prerequisite must come from the public index")
    return requirements


def rebuild(guard, project: Path, work: Path) -> tuple[Path, dict]:
    bootstrap = guard.sibling("bootstrap")
    venv = work / "build-env"
    python = bootstrap.create(venv, Path(sys.prefix) / bootstrap.PIN["filename"])
    environment = bootstrap.environment(work)
    report = work / "build-prerequisites.json"
    resolver = Path(__file__).with_name("resolve.py").resolve()
    subprocess.run(
        [str(python), "-I", str(resolver), "install", "--no-cache-dir", "--disable-pip-version-check",
         "--only-binary=:all:", "--index-url", guard.PUBLIC_INDEX, "--report", str(report),
         *build_requirements(guard, project)],
        env=environment, cwd=work, check=True, timeout=600,
    )
    environment["PATH"] = str(python.parent) + os.pathsep + os.defpath
    # Use the already-provisioned native toolchain, never install or switch it.
    # Cargo's dependency/build cache is fresh; runner source overrides are absent.
    cargo = shutil.which("cargo")
    if cargo:
        environment["PATH"] += os.pathsep + str(Path(cargo).parent)
        environment["RUSTUP_HOME"] = os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup"))
        environment["CARGO_HOME"] = str(work / "cargo-home")
    output = work / "rebuilt"
    subprocess.run(
        [str(python), "-I", "-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation",
         "--no-cache-dir", "--disable-pip-version-check", "--wheel-dir", str(output), str(project)],
        env=environment, cwd=work, check=True, timeout=600,
    )
    wheels = guard.wheel_set(output)
    guard.require(len(wheels) == 1, "source rebuild must produce exactly one wheel")
    return wheels[0], json.loads(report.read_text())


def check(guard, directory: Path, receipt: Path, raw: str, evidence: Path) -> None:
    receipt.unlink(missing_ok=True)
    archives = list(directory.iterdir())
    guard.require(len(archives) == 1, "source job must contain exactly one archive")
    archive = archives[0]
    guard.require(archive.name.endswith(".tar.gz") and archive.is_file() and not archive.is_symlink(),
                  "source job requires a regular tar.gz archive")
    identity = guard.identity()
    guard.sibling("targets").validate("linux-x86_64", guard.observed_context())
    original = guard.digest(archive)
    with tempfile.TemporaryDirectory(prefix="sdist-readiness-") as temporary:
        work = Path(temporary)
        project = extract(archive, work / "source")
        wheel, prerequisites = rebuild(guard, project, work)
        proof_path = work / "wheel-proof.json"
        # This contract deliberately promises one Linux CPython source rebuild,
        # not source builds on untested operating systems/toolchains.
        previous = os.environ.get("READINESS_TARGET")
        os.environ["READINESS_TARGET"] = "linux-x86_64"
        try:
            guard.check(wheel.parent, proof_path, raw)
        finally:
            if previous is None:
                os.environ.pop("READINESS_TARGET", None)
            else:
                os.environ["READINESS_TARGET"] = previous
        proof = json.loads(proof_path.read_text())
        evidence.mkdir(parents=True, exist_ok=True)
        guard.require(not list(evidence.iterdir()), "source evidence directory is not empty")
        shutil.copyfile(wheel, evidence / wheel.name)
    guard.require(guard.digest(archive) == original, "source archive changed during rebuild")
    guard.require(guard.identity() == identity, "source identity changed during rebuild")
    receipt.write_text(json.dumps({"archive": {"file": archive.name, "sha256": original},
                                  "build_prerequisites": prerequisites,
                                  "rebuilt_wheel_proof": proof}, indent=2) + "\n")
