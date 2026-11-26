"""Resolve ``mod name;`` declarations of a Rust test target to their files.

A cargo integration test is a target root: ``tests/<name>.rs``. Its
``mod support;`` loads ``tests/support.rs`` or ``tests/support/mod.rs``, and a
child that is not a ``mod.rs`` resolves its own declarations below a directory
named for it, exactly as the compiler does. A declared child that is absent
from the tree is ``CannotRun``: a hook that read the parent alone would report
a verdict on code it never saw (PIPE-GATES-R082).
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path, PurePosixPath

from pipelines_hooks.core.errors import CannotRun

_DECLARATION = re.compile(
    r"^(?P<attributes>(?:[ \t]*#\[[^\]\n]*\][ \t]*\n)*)"
    r"[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?mod[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*;",
    re.MULTILINE,
)
_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
_PATH_ATTRIBUTE = re.compile(r'#\[\s*path\s*=\s*"([^"]+)"\s*\]')


def is_test_target_root(tree: Path, path: str) -> bool:
    """``<crate>/tests/<name>.rs``: a cargo integration-test target of a crate in ``tree``."""
    posix = PurePosixPath(path)
    crate = posix.parent.parent
    return posix.suffix == ".rs" and posix.parent.name == "tests" and (tree / crate / "Cargo.toml").is_file()


def declared_modules(source: str) -> list[tuple[str, str | None]]:
    """``(name, #[path] value or None)`` of each file-backed ``mod x;`` declaration."""
    found: list[tuple[str, str | None]] = []
    for match in _DECLARATION.finditer(_COMMENT.sub("", source)):
        attribute = _PATH_ATTRIBUTE.search(match.group("attributes"))
        found.append((match.group("name"), attribute.group(1) if attribute else None))
    return found


def _child_directory(path: PurePosixPath, *, target_root: bool) -> PurePosixPath:
    if target_root or path.name == "mod.rs":
        return path.parent
    return path.parent / path.stem


def resolve_children(tree: Path, path: str) -> list[str]:
    """Every file a test target reaches through ``mod`` declarations, depth first.

    Reads the staged bytes in ``tree``. A ``#[path = "x.rs"]`` declaration loads
    ``x.rs`` relative to the declaring file's directory, and that child resolves
    its own declarations as a ``mod.rs`` does. Raises :class:`CannotRun` for a
    declared child with no file.
    """
    found: list[str] = []
    pending = [(PurePosixPath(path), True)]
    seen = {path}
    while pending:
        current, target_root = pending.pop()
        file = tree / current.as_posix()
        try:
            source = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise CannotRun(f"cannot read {current} while resolving its test modules: {exc}") from exc
        base = _child_directory(current, target_root=target_root)
        for name, explicit in declared_modules(source):
            candidates = (
                (PurePosixPath(posixpath.normpath((current.parent / explicit).as_posix())),)
                if explicit
                else (
                    base / f"{name}.rs",
                    base / name / "mod.rs",
                )
            )
            child = next((c for c in candidates if (tree / c.as_posix()).is_file()), None)
            if child is None:
                looked = " nor ".join(map(str, candidates))
                raise CannotRun(f"{current} declares `mod {name};` but neither {looked} is staged or tracked")
            if child.as_posix() not in seen:
                seen.add(child.as_posix())
                found.append(child.as_posix())
                pending.append((child, bool(explicit)))
    return found
