"""A gate source without a working copy: files by path and blob digest.

A gate set runs against a source, not a checkout. The source answers two
questions: which files exist under a prefix, with each blob's digest and
size, and what one blob's bytes are. The digest binds the bytes to the
path, so a gate never inspects content the source did not declare. The
disk provider serves one directory tree; the engine tree provider serves
an epistemic-graph revision the same way once its tree reads ship
(MEDULLA-SCM-R004).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pipelines_hooks.core.errors import CannotRun

#: Directory names that are checkout metadata, not tree content.
CHECKOUT_METADATA_DIRS = frozenset({".git"})


@dataclass(frozen=True)
class FileEntry:
    """One declared file: its relative path, blob digest and size."""

    path: str
    digest: str
    size: int


class FileProvider(Protocol):
    """The reads a gate needs of a source that is not a working copy."""

    def list_files(self, prefix: str = "") -> tuple[FileEntry, ...]:
        """Every declared file under ``prefix`` (the whole tree for ``""``)."""
        ...

    def read(self, path: str) -> bytes:
        """One blob's bytes, bound to the digest recorded for ``path``."""
        ...


def blob_digest(data: bytes) -> str:
    """The content digest of one blob, in the ledger's ``sha256:<hex>`` form."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


class DiskProvider:
    """Serves one directory tree by path and blob digest; no git, no checkout.

    Listing hashes every blob once. A later :meth:`read` re-hashes the
    bytes and fails closed when they no longer match the declared digest,
    so a source that moves under a running gate cannot feed it stale
    content.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        if not self._root.is_dir():
            raise CannotRun(f"source provider: {self._root} is not a directory")
        self._entries: dict[str, FileEntry] = {entry.path: entry for entry in self._list()}

    def _list(self) -> list[FileEntry]:
        found: list[FileEntry] = []
        for path in self._root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(self._root).as_posix()
            if any(part in CHECKOUT_METADATA_DIRS for part in relative.split("/")):
                continue
            blob = path.read_bytes()
            found.append(FileEntry(path=relative, digest=blob_digest(blob), size=len(blob)))
        return sorted(found, key=lambda entry: entry.path)

    def list_files(self, prefix: str = "") -> tuple[FileEntry, ...]:
        """The declared files under one prefix; ``""`` is the whole tree."""
        wanted = f"{prefix}/" if prefix else ""
        return tuple(entry for entry in self._entries.values() if entry.path.startswith(wanted))

    def read(self, path: str) -> bytes:
        entry = self._entries.get(path)
        if entry is None:
            raise CannotRun(f"source provider: {path} is not a declared file")
        blob = (self._root / path).read_bytes()
        if blob_digest(blob) != entry.digest:
            raise CannotRun(f"source provider: {path} no longer matches its declared digest {entry.digest}")
        return blob
