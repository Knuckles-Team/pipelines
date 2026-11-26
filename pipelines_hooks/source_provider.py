"""A gate source without a working copy: files by path and blob digest.

A gate set runs against a source, not a checkout. The source answers two
questions: which files exist under a prefix, with each blob's digest and
size, and what one blob's bytes are. The digest binds the bytes to the
path, so a gate never inspects content the source did not declare. The
disk provider serves one directory tree; the engine tree provider serves
one engine repository ref through the arbora ``source.tree`` and
``source.blob`` operations the same way (PIPE-GATES-R003), so a blocking
gate lands a changeset without a working copy.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.verdict_publish import post_operation
from pipelines_hooks.core.gitenv import EXTRACTED_TREE_MARKER

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
            if relative == EXTRACTED_TREE_MARKER or any(part in CHECKOUT_METADATA_DIRS for part in relative.split("/")):
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


def tree_digest(source: Path) -> str:
    """The digest of one tree's canonical listing: every path with its blob digest, in path order."""
    listing = "".join(f"{entry.path}\0{entry.digest}\n" for entry in DiskProvider(source).list_files())
    return blob_digest(listing.encode("utf-8"))


#: One served-operation call: ``(operation, params) -> result``.
OperationCall = Callable[[str, Mapping[str, Any]], Any]

#: The size a tree listing cannot declare; the blob read reports the real one.
UNDECLARED_SIZE = -1


class EngineTreeProvider:
    """Serves one engine repository ref by path and blob digest; no checkout, no git.

    The tree is listed once through ``source.tree`` (directories are walked
    breadth first; the engine projection stores no directory nodes) and each
    blob is read through ``source.blob``. A blob whose bytes do not match the
    digest the listing declared, or whose digest is not a ``sha256:`` blob
    digest, fails closed: a gate never inspects content the engine did not
    declare.
    """

    def __init__(
        self,
        endpoint: str,
        token: str,
        repository: str,
        ref: str,
        *,
        call: OperationCall | None = None,
    ) -> None:
        if not endpoint:
            raise CannotRun("engine tree provider: no arbora endpoint is configured")
        self._identity = {"repository": repository, "ref": ref}
        self._call: OperationCall = call or (
            lambda operation, params: post_operation(endpoint, token, operation, params)
        )
        self._entries: dict[str, FileEntry] = {entry.path: entry for entry in self._list()}

    def _invoke(self, operation: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            outcome = self._call(operation, {**self._identity, **params})
        except OSError as exc:
            raise CannotRun(f"engine tree provider: {exc}") from None
        if not isinstance(outcome, Mapping) or outcome.get("found") is not True:
            reason = outcome.get("reason") if isinstance(outcome, Mapping) else None
            raise CannotRun(f"engine tree provider: {operation} found nothing ({reason or 'no reason given'})")
        return outcome

    def _list(self) -> list[FileEntry]:
        found: list[FileEntry] = []
        pending, seen = [""], set()
        while pending:
            directory = pending.pop(0)
            if directory in seen:
                continue
            seen.add(directory)
            for raw in self._invoke("source.tree", {"path": directory}).get("entries", ()):
                path, kind = str(raw.get("path", "")), raw.get("kind")
                if not path or path.startswith("/") or ".." in path.split("/"):
                    raise CannotRun(f"engine tree provider: unsafe tree path {path!r}")
                if kind == "directory":
                    pending.append(path)
                elif kind == "file":
                    found.append(
                        FileEntry(path=path, digest=str(raw.get("content_digest") or ""), size=UNDECLARED_SIZE)
                    )
        return sorted(found, key=lambda entry: entry.path)

    def list_files(self, prefix: str = "") -> tuple[FileEntry, ...]:
        """The declared files under one prefix; ``""`` is the whole tree."""
        wanted = f"{prefix}/" if prefix else ""
        return tuple(entry for entry in self._entries.values() if entry.path.startswith(wanted))

    def read(self, path: str) -> bytes:
        entry = self._entries.get(path)
        if entry is None:
            raise CannotRun(f"source provider: {path} is not a declared file")
        outcome = self._invoke("source.blob", {"path": path})
        content = outcome.get("content", "")
        try:
            blob = (
                base64.b64decode(content, validate=True)
                if outcome.get("content_encoding") == "base64"
                else str(content).encode("utf-8")
            )
        except (binascii.Error, ValueError):
            raise CannotRun(f"source provider: {path} came back undecodable") from None
        if not entry.digest.startswith("sha256:") or blob_digest(blob) != entry.digest:
            raise CannotRun(f"source provider: {path} does not match its declared digest {entry.digest or '(none)'}")
        return blob


def verify_tree(provider: FileProvider, receipt: Mapping[str, str]) -> list[str]:
    """Every path of an extracted tree that disagrees with the receipt's hashes.

    Compares each listed file's recomputed content digest with the digest the
    receipt declares. A path whose digest differs, a declared path that is
    missing and a listed path the receipt does not declare are each reported.
    Git is never consulted: the tree has no working copy to diff.
    """
    findings: list[str] = []
    listed = {entry.path for entry in provider.list_files()}
    for path in sorted(listed):
        expected = receipt.get(path)
        if expected is None:
            findings.append(f"{path}: undeclared (not in the receipt)")
        elif blob_digest(provider.read(path)) != expected:
            findings.append(f"{path}: digest differs from the receipt ({expected})")
    findings.extend(f"{path}: missing (declared by the receipt)" for path in sorted(set(receipt) - listed))
    return findings
