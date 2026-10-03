"""Pinned jscpd source identity and offline installed-build verification."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import tempfile
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env

SOURCE_COMMIT = "56b65069a22073505f6813dfdfbf302880066dfb"
SOURCE_TREE = "49025f8175a046e5e398271719aad950a46dd203"
PATCHED_TREE = "eb78e91a60a0d8fc6c45ad629f428fda3ecc8e8b"
ARCHIVE_URL = f"https://codeload.github.com/kucherenko/jscpd/tar.gz/{SOURCE_COMMIT}"
ARCHIVE_SHA256 = "3ba10661d3c61034a1c6c9d1387acab0af4ef313062327bb14ebacf6ab9ade50"
PATCH_SHA256 = "c0403911dfd8d52f4d88b9c17e54a2b75b391d764a123eaad9940fd4a26dab78"
LOCK_SHA256 = "9bd475c6bfb2615d292c64a1b988654afa6a73fe0039b5b077312a65c35ab57a"
RUST_TOOLCHAIN = "1.97.0"


def sha256(path: Path) -> str:
    """Hash a bounded provisioned file without loading it all into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_identity() -> dict[str, str]:
    """All build inputs shared by provisioning, cache selection and verification."""
    return {
        "source_commit": SOURCE_COMMIT,
        "source_tree": SOURCE_TREE,
        "patched_tree": PATCHED_TREE,
        "archive_sha256": ARCHIVE_SHA256,
        "patch_sha256": PATCH_SHA256,
        "lock_sha256": LOCK_SHA256,
        "rust_toolchain": RUST_TOOLCHAIN,
        "profile": "debug",
        "os": platform.system(),
        "architecture": platform.machine(),
    }


def cache_key() -> str:
    return hashlib.sha256(
        json.dumps(build_identity(), sort_keys=True).encode()
    ).hexdigest()


def _validated_receipt(executable: Path) -> dict:
    receipt = json.loads(executable.with_suffix(".provenance.json").read_text())
    if receipt.get("identity") != build_identity():
        raise ValueError("source/toolchain/platform identity mismatch")
    if receipt.get("binary_sha256") != sha256(executable):
        raise ValueError("executable checksum mismatch")
    if not receipt.get("compiler", "").startswith(f"rustc {RUST_TOOLCHAIN} "):
        raise ValueError("compiler identity mismatch")
    return receipt


def verify_receipt(executable: Path) -> dict:
    """Reject missing, stale or mutated artifacts before any gate uses them."""
    try:
        return _validated_receipt(executable)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise CannotRun(f"jscpd provenance rejected for {executable}: {exc}") from exc


def _scan(executable: str, root: Path, files: dict[str, str]) -> list[dict]:
    source = root / "source"
    source.mkdir()
    for name, text in files.items():
        (source / name).write_text(text, encoding="utf-8")
    output = root / "report"
    result = subprocess.run(
        [
            executable,
            str(source),
            "--workers",
            "1",
            "--min-tokens",
            "50",
            "--min-lines",
            "5",
            "--mode",
            "mild",
            "--format",
            "markdown",
            "--reporters",
            "json",
            "--output",
            str(output),
        ],
        env=sanitized_env(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"probe exited {result.returncode}")
    report = json.loads((output / "jscpd-report.json").read_text())
    if not isinstance(report.get("duplicates"), list):
        raise TypeError("probe report lacks duplicates")
    return report["duplicates"]


def require_corrected_build(executable: str) -> None:
    """Verify provenance and negative/positive probes; never install or download."""
    executable = str(Path(executable).resolve())
    verify_receipt(Path(executable))
    try:
        version = subprocess.run(
            [executable, "--version"],
            env=sanitized_env(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if version.returncode or version.stdout.strip() != "cpd 5.0.16":
            raise ValueError("scanner version mismatch")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"jscpd version verification failed: {exc}") from exc
    try:
        _verify_probes(executable)
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"jscpd corrected-build probe failed: {exc}") from exc


def _verify_probes(executable: str) -> None:
    letters = "\n".join(["abcdefghijklmno"] * 8)
    digits = "\n".join(["987654321009876"] * 8)
    prose = "\n".join(
        f"Chapter {i} explains operational requirements for docs/*.md with concrete verification evidence and explicit outcomes."
        for i in range(8)
    )
    with tempfile.TemporaryDirectory(prefix="jscpd-build-probe-") as tmp:
        root = Path(tmp)
        for name in ("negative", "positive"):
            (root / name).mkdir()
        negative = _scan(
            executable,
            root / "negative",
            {
                "a.md": f"Read docs/*.md\n\n```text\n{letters}\n```\n",
                "b.md": f"Read other/*.rst\n\n```text\n{digits}\n```\n",
            },
        )
        positive = _scan(executable, root / "positive", {"a.md": prose, "b.md": prose})
        if negative or not any(x.get("format") == "markdown" for x in positive):
            raise ValueError("Markdown false-positive/true-positive contract failed")
