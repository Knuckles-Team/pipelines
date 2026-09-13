"""Repository-relative path handling shared by every scanner wrapper."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path, PurePosixPath, PureWindowsPath


def normalise_path(path: str | Path) -> str:
    """Forward slashes and no leading ``./``, without deleting dot names."""
    value = os.fspath(path)
    if not isinstance(value, str):
        raise ValueError("path must be a text path, not bytes")
    value = value.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def relative_to_root(path: str | Path, root: Path) -> str:
    """A safe repository-relative path; an escape from ``root`` raises.

    Scanner reports carry absolute or relative paths. Both are accepted only
    when they resolve under ``root``; ``..`` traversal, foreign absolute paths
    and Windows drives are rejected by raising :class:`ValueError`.
    """
    raw = normalise_path(path)
    if not raw or "\x00" in raw:
        raise ValueError("path must be a non-empty, NUL-free string")
    if PureWindowsPath(raw).drive:
        raise ValueError(f"path {raw!r} uses an unsupported Windows drive")
    posix = PurePosixPath(raw)
    candidate = Path(raw) if posix.is_absolute() else root / Path(*posix.parts)
    resolved_root = root.resolve(strict=False)
    try:
        relative = candidate.resolve(strict=False).relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path {raw!r} escapes {resolved_root}") from exc
    return "" if relative == Path(".") else relative.as_posix()


def _contains_segments(value: str, prefix: str) -> bool:
    segments = value.split("/")
    wanted = prefix.split("/")
    limit = len(segments) - len(wanted) + 1
    return any(segments[start : start + len(wanted)] == wanted for start in range(limit))


def _matches_directory_suffix(value: str, pattern: str) -> bool:
    if not pattern.endswith("/**"):
        return False
    prefix = pattern[:-3].rstrip("/")
    if prefix.startswith("**/"):
        return _contains_segments(value, prefix[3:])
    return value == prefix or value.startswith(prefix + "/")


def _matches_recursive(value: str, pattern: str) -> bool:
    if not pattern.startswith("**/"):
        return False
    if fnmatch.fnmatchcase(value, pattern[3:]):
        return True
    return PurePosixPath(value).match(pattern)


def glob_match(path: str, pattern: str) -> bool:
    """Match a ``**`` glob at the root and at any depth.

    ``fnmatch`` treats ``**/`` as requiring a slash, so ``**/target/**`` would
    miss a root-level ``target`` directory. A pattern without a leading ``**/``
    is root-anchored, matching native scanner walker semantics.
    """
    value = normalise_path(path)
    pattern = normalise_path(pattern)
    return (
        fnmatch.fnmatchcase(value, pattern)
        or _matches_recursive(value, pattern)
        or _matches_directory_suffix(value, pattern)
    )


def under_any(path: str, prefixes: tuple[str, ...]) -> bool:
    """Whether ``path`` is one of ``prefixes`` or nested below one."""
    value = normalise_path(path)
    return any(
        value == prefix or value.startswith(prefix.rstrip("/") + "/")
        for prefix in (normalise_path(item) for item in prefixes)
    )
