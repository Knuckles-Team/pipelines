#!/usr/bin/env python3
"""Provision the audited jscpd build in an explicitly supplied isolated prefix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pipelines_hooks.core import jscpd_build as contract
from pipelines_hooks.core.gitenv import sanitized_env


def run(*args: str, cwd: Path | None = None) -> str:
    env = sanitized_env()
    if cwd is not None:
        env["GIT_CEILING_DIRECTORIES"] = str(cwd.parent)
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        timeout=1200,
        check=True,
    )
    return result.stdout.strip()


def verify_hash(path: Path, expected: str) -> None:
    if contract.sha256(path) != expected:
        raise ValueError(f"checksum mismatch: {path.name}")


def _tree_entry(path: Path) -> tuple[str, bytes]:
    if path.is_symlink():
        body, mode = os.readlink(path).encode(), b"120000"
    elif path.is_dir():
        return (
            path.name + "/",
            b"40000 " + path.name.encode() + b"\0" + bytes.fromhex(tree_hash(path)),
        )
    else:
        body = path.read_bytes()
        mode = b"100755" if path.stat().st_mode & 0o111 else b"100644"
    digest = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).digest()
    return path.name, mode + b" " + path.name.encode() + b"\0" + digest


def tree_hash(root: Path) -> str:
    """Compute Git's tree identity without trusting checkout metadata."""
    entries = (_tree_entry(path) for path in root.iterdir() if path.name != ".git")
    body = b"".join(value for _, value in sorted(entries))
    return hashlib.sha1(b"tree " + str(len(body)).encode() + b"\0" + body).hexdigest()


def obtain_archive(dest: Path) -> None:
    with (
        urllib.request.urlopen(contract.ARCHIVE_URL, timeout=45) as response,
        dest.open("wb") as output,
    ):
        if response.url != contract.ARCHIVE_URL:
            raise ValueError("unexpected source archive redirect")
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > 32 * 1024 * 1024:
                raise ValueError("source archive exceeds 32 MiB")
            output.write(chunk)
    verify_hash(dest, contract.ARCHIVE_SHA256)


def prepare_source(archive: Path, patch: Path, work: Path) -> Path:
    verify_hash(archive, contract.ARCHIVE_SHA256)
    verify_hash(patch, contract.PATCH_SHA256)
    with tarfile.open(archive) as bundle:
        if sum(m.size for m in bundle.getmembers()) > 128 * 1024 * 1024:
            raise ValueError("expanded source exceeds 128 MiB")
        bundle.extractall(work, filter="data")
    source = work / f"jscpd-{contract.SOURCE_COMMIT}"
    if tree_hash(source) != contract.SOURCE_TREE:
        raise ValueError("upstream source tree mismatch")
    verify_hash(source / "rust/Cargo.lock", contract.LOCK_SHA256)
    run("git", "apply", "--check", str(patch), cwd=source)
    run("git", "apply", str(patch), cwd=source)
    if tree_hash(source) != contract.PATCHED_TREE:
        raise ValueError("patched source tree mismatch")
    verify_hash(source / "rust/Cargo.lock", contract.LOCK_SHA256)
    return source


def install(prefix: Path, archive: Path | None = None) -> Path:
    destination = prefix / contract.cache_key()
    executable = destination / "bin/jscpd"
    if executable.exists():
        contract.require_corrected_build(str(executable))
        return executable
    destination.mkdir(parents=True, exist_ok=True)
    patch = REPO / "scripts/patches/jscpd-markdown-glob.patch"
    compiler = run("rustup", "run", contract.RUST_TOOLCHAIN, "rustc", "--version")
    if not compiler.startswith("rustc 1.97.0 "):
        raise ValueError("pinned Rust compiler unavailable")
    with tempfile.TemporaryDirectory(prefix="build-", dir=destination) as tmp:
        work = Path(tmp)
        staged = _build(work, archive, patch)
        receipt = {
            "identity": contract.build_identity(),
            "compiler": compiler,
            "binary_sha256": contract.sha256(staged),
        }
        _publish(staged, executable, receipt)
    return executable


def _publish(staged: Path, executable: Path, receipt: dict) -> None:
    staged.with_suffix(".provenance.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    contract.require_corrected_build(str(staged))
    executable.parent.mkdir(exist_ok=True)
    shutil.copy2(
        staged.with_suffix(".provenance.json"),
        executable.with_suffix(".provenance.json"),
    )
    os.replace(staged, executable)
    print(json.dumps(receipt, sort_keys=True), file=sys.stderr)


def _build(work: Path, archive: Path | None, patch: Path) -> Path:
    if archive is None:
        archive = work / "source.tar.gz"
        obtain_archive(archive)
    source = prepare_source(archive.resolve(), patch.resolve(), work / "unpacked")
    target = work / "target"
    run(
        "rustup",
        "run",
        contract.RUST_TOOLCHAIN,
        "cargo",
        "build",
        "--locked",
        "-p",
        "jscpd",
        "--bin",
        "cpd",
        "-j",
        "2",
        "--target-dir",
        str(target),
        cwd=source / "rust",
    )
    staged = work / "jscpd"
    shutil.copy2(target / "debug/cpd", staged)
    return staged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    print(install(args.root.resolve(), args.archive).parent)


if __name__ == "__main__":
    main()
