"""Safe filesystem helpers for the Pages readiness contract."""

from __future__ import annotations

import json
import os
import tempfile
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any

from .constants import MAX_HTML_BYTES, MAX_MANIFEST_BYTES, PATH_CONTROL_PATTERN
from .errors import _fail


def _safe_root(value: str | Path) -> Path:
    root = Path(value).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    try:
        resolved = root.resolve(strict=True)
        metadata = root.lstat()
    except (OSError, RuntimeError):
        _fail("root-unavailable")
    if root.is_symlink() or resolved != root.absolute() or not root.is_dir():
        _fail("root-invalid")
    if metadata.st_nlink < 1:
        _fail("root-invalid")
    return resolved


def _path_parts(raw: object, label: str) -> tuple[str, ...]:
    if isinstance(raw, Path):
        raw = raw.as_posix()
    if not isinstance(raw, str) or not raw or "\\" in raw:
        _fail(f"{label}-path-invalid")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or not relative.parts:
        _fail(f"{label}-path-invalid")
    if any(
        part in {"", ".", ".."} or PATH_CONTROL_PATTERN.search(part)
        for part in relative.parts
    ):
        _fail(f"{label}-path-invalid")
    return relative.parts


def _reject_symlink_components(root: Path, candidate: Path, label: str) -> None:
    try:
        relative = candidate.absolute().relative_to(root.absolute())
    except ValueError:
        _fail(f"{label}-containment")
    cursor = root
    for part in relative.parts:
        cursor /= part
        try:
            if cursor.is_symlink():
                _fail(f"{label}-symlink")
        except OSError:
            _fail(f"{label}-unavailable")


def _safe_existing_path(
    root: Path, raw: object, label: str, *, directory: bool = False
) -> Path:
    parts = _path_parts(raw, label)
    candidate = root.joinpath(*parts)
    _reject_symlink_components(root, candidate, label)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        _fail(f"{label}-containment")
    if directory and (not resolved.is_dir() or resolved.is_symlink()):
        _fail(f"{label}-not-directory")
    return resolved


_safe_existing_dir = partial(_safe_existing_path, directory=True)


def _safe_site(root: Path, raw: str | Path) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        return _safe_existing_path(root, candidate, "site")
    _reject_symlink_components(root, candidate, "site")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        _fail("site-containment")
    if resolved.is_symlink() or not resolved.is_dir():
        _fail("site-invalid")
    return resolved


def _regular_bytes(path: Path, label: str, limit: int) -> bytes:
    try:
        metadata = path.lstat()
    except OSError:
        _fail(f"{label}-unavailable")
    if path.is_symlink() or not path.is_file() or metadata.st_nlink != 1:
        _fail(f"{label}-not-regular")
    if metadata.st_size > limit:
        _fail(f"{label}-oversize")
    try:
        payload = path.read_bytes()
    except OSError:
        _fail(f"{label}-unreadable")
    if len(payload) > limit:
        _fail(f"{label}-oversize")
    return payload


def _read_json(
    path: Path, label: str, limit: int = MAX_MANIFEST_BYTES
) -> dict[str, Any]:
    payload = _regular_bytes(path, label, limit)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(f"{label}-invalid-json")
    if not isinstance(value, dict):
        _fail(f"{label}-root-invalid")
    return value


def _safe_output_path(site: Path, relative: str, label: str) -> Path:
    parts = _path_parts(relative, label)
    candidate = site.joinpath(*parts)
    _reject_symlink_components(site, candidate, label)
    try:
        candidate.absolute().relative_to(site.absolute())
    except ValueError:
        _fail(f"{label}-containment")
    if candidate.exists() and candidate.is_symlink():
        _fail(f"{label}-symlink")
    if candidate.exists() and not candidate.is_file():
        _fail(f"{label}-not-regular")
    return candidate


def _temporary_payload(
    path: Path, payload: bytes, holder: list[Path | None]
) -> None:
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False
    ) as handle:
        holder[0] = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write(path: Path, payload: bytes, label: str) -> None:
    parent = path.parent
    _reject_symlink_components(parent.parent, parent, label)
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        _fail(f"{label}-parent-invalid")
    parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _regular_bytes(path, label, max(len(payload), MAX_HTML_BYTES))
        if path.read_bytes() == payload:
            return
    temporary: list[Path | None] = [None]
    try:
        _temporary_payload(path, payload, temporary)
        os.replace(temporary[0], path)
    except OSError:
        if temporary[0] is not None:
            temporary[0].unlink(missing_ok=True)
        _fail(f"{label}-write-failed")
    temporary[0] = None
