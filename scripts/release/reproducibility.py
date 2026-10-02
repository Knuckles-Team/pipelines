"""Byte-identical wheel reproducibility (PIPE-RELEASE-R003 remaining half).

Build a pure-Python package's wheel twice, in two independent directories
with a shared ``SOURCE_DATE_EPOCH``, and compare the two artifacts byte for
byte. A real release build job runs this as its reproducibility check; it
never substitutes a hash comparison of unpacked contents for the actual
published bytes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .errors import ReproducibilityError

_BUILD_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class ReproducibilityResult:
    """Whether two wheel builds are byte-identical, and where they differ otherwise."""

    identical: bool
    differences: tuple[str, ...] = ()


def build_wheel_twice(source_dir: Path, out_dir_a: Path, out_dir_b: Path, *, source_date_epoch: str) -> tuple[Path, Path]:
    """Build ``source_dir`` into two fresh output directories; the two wheel paths."""
    return _build_once(source_dir, out_dir_a, source_date_epoch), _build_once(source_dir, out_dir_b, source_date_epoch)


def compare_wheels(wheel_a: Path, wheel_b: Path) -> ReproducibilityResult:
    """Byte-for-byte comparison, with a per-member diagnosis when they differ."""
    if wheel_a.read_bytes() == wheel_b.read_bytes():
        return ReproducibilityResult(identical=True)
    return ReproducibilityResult(identical=False, differences=_member_differences(wheel_a, wheel_b))


def _build_once(source_dir: Path, out_dir: Path, source_date_epoch: str) -> Path:
    _clean_build_artifacts(source_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "SOURCE_DATE_EPOCH": source_date_epoch}
    command = [sys.executable, "-m", "build", "--no-isolation", "--wheel", "-o", str(out_dir)]
    result = subprocess.run(command, cwd=source_dir, env=env, capture_output=True, text=True, timeout=_BUILD_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise ReproducibilityError(f"wheel build failed in {out_dir}: {result.stderr.strip()}")
    return _single_wheel(out_dir)


def _single_wheel(out_dir: Path) -> Path:
    wheels = sorted(out_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise ReproducibilityError(f"expected exactly one wheel in {out_dir}, found {len(wheels)}")
    return wheels[0]


def _clean_build_artifacts(source_dir: Path) -> None:
    shutil.rmtree(source_dir / "build", ignore_errors=True)
    for egg_info in source_dir.glob("**/*.egg-info"):
        shutil.rmtree(egg_info, ignore_errors=True)


def _member_differences(wheel_a: Path, wheel_b: Path) -> tuple[str, ...]:
    with zipfile.ZipFile(wheel_a) as archive_a, zipfile.ZipFile(wheel_b) as archive_b:
        members_a = _members(archive_a)
        members_b = _members(archive_b)
    lines = []
    for name in sorted(set(members_a) | set(members_b)):
        lines.extend(_member_diff(name, members_a, members_b))
    return tuple(lines)


def _members(archive: zipfile.ZipFile) -> dict[str, tuple[tuple[int, ...], bytes]]:
    return {info.filename: (info.date_time, archive.read(info.filename)) for info in archive.infolist()}


def _member_diff(name: str, members_a: dict, members_b: dict) -> list[str]:
    if name not in members_a:
        return [f"{name}: only in the second build"]
    if name not in members_b:
        return [f"{name}: only in the first build"]
    date_a, data_a = members_a[name]
    date_b, data_b = members_b[name]
    if data_a != data_b:
        return [f"{name}: content differs"]
    if date_a != date_b:
        return [f"{name}: timestamp differs"]
    return []
