"""Digest-pinned exceptions for a historical secret match (PIPE-GATES-R083).

Some credential patterns are shape-based, so an old commit can keep matching a
line that was never a secret. History is not rewritten for that. The consumer
records the occurrence in ``.config/secret-history-exceptions.toml``::

    [[exception]]
    commit = "<full commit digest that added the line>"
    file = "path/at/that/commit"
    line_digest = "sha256:<hex of the added line, stripped>"
    reason = "why the line is not a credential (at least 12 words)"
    reviewed_on = "YYYY-MM-DD"

An entry exempts exactly one occurrence: that line, in that file, added by that
commit. The same line added by any other commit, or a different line in the same
commit, is still a hit. ``secret-history --self-check`` proves each entry still
describes a real, credential-shaped occurrence, so an entry that no longer
matches its pin fails instead of silently exempting nothing.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, run_git

EXCEPTIONS = ".config/secret-history-exceptions.toml"
NET_DIFF = "net-diff"
_FIELDS = ("commit", "file", "line_digest", "reason", "reviewed_on")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def line_digest(content: str) -> str:
    """The pinned digest of one added line, as ``sha256:<hex>`` of the stripped text."""
    return "sha256:" + hashlib.sha256(content.strip().encode("utf-8", "surrogatepass")).hexdigest()


@dataclass(frozen=True)
class HistoryException:
    commit: str
    file: str
    line_digest: str
    reason: str
    reviewed_on: str

    def pins(self, commit: str, file: str, content: str) -> bool:
        return (
            commit == self.commit and file.removeprefix("b/") == self.file and line_digest(content) == self.line_digest
        )


def _entry(index: int, raw: object) -> HistoryException:
    label = f"{EXCEPTIONS} entry {index}"
    if not isinstance(raw, dict) or any(not isinstance(raw.get(f), str) or not raw[f].strip() for f in _FIELDS):
        raise CannotRun(f"{label} must set every field: {', '.join(_FIELDS)}")
    if not _COMMIT.fullmatch(raw["commit"]):
        raise CannotRun(f"{label}: commit must be a full commit digest, not an abbreviation or a ref")
    if not _DIGEST.fullmatch(raw["line_digest"]):
        raise CannotRun(f"{label}: line_digest must be sha256:<64 hex>")
    if len(raw["reason"].split()) < 12:
        raise CannotRun(f"{label} has no real justification (a reviewed claim says WHY)")
    return HistoryException(**{field: raw[field] for field in _FIELDS})


def load_exceptions(root: Path) -> list[HistoryException]:
    """The repository's entries; a repository without the file has none."""
    path = root / EXCEPTIONS
    if not path.is_file():
        return []
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"{EXCEPTIONS} is unreadable: {exc}") from exc
    entries = document.get("exception", [])
    if not isinstance(entries, list):
        raise CannotRun(f"{EXCEPTIONS}: `exception` must be an array of tables")
    return [_entry(index, entry) for index, entry in enumerate(entries)]


def _reachable(root: Path, commit: str) -> bool:
    return run_git(root, ("merge-base", "--is-ancestor", commit, "HEAD")).returncode == 0


class Exemptions:
    """The predicate ``scan_credentials`` consults before it reports a line."""

    def __init__(self, root: Path, entries: list[HistoryException]) -> None:
        self._root = root
        self._entries = entries
        self._live: dict[str, bool] = {}

    def _reaches_head(self, commit: str) -> bool:
        if commit not in self._live:
            self._live[commit] = _reachable(self._root, commit)
        return self._live[commit]

    def __call__(self, commit: str, file: str, content: str) -> bool:
        for entry in self._entries:
            if entry.pins(entry.commit if commit == NET_DIFF else commit, file, content):
                # The net diff has no commit of its own: it carries the pinned line only when
                # the pinned commit is in the history under scan.
                if commit != NET_DIFF or self._reaches_head(entry.commit):
                    return True
        return False


def exemptions(root: Path) -> Exemptions | None:
    entries = load_exceptions(root)
    return Exemptions(root, entries) if entries else None


def pin_problem(root: Path, entry: HistoryException) -> str | None:
    """Why an entry no longer describes a real credential-shaped occurrence, or ``None``."""
    from pipelines_hooks.security.history_scan import COMMIT_MARK, added_lines, scan_credentials

    label = f"{entry.file}@{entry.commit[:12]}"
    if run_git(root, ("cat-file", "-e", f"{entry.commit}^{{commit}}")).returncode != 0:
        return f"{label}: the pinned commit is not in this history"
    patch = git_text(root, ("show", "--no-color", "--no-ext-diff", "-U0", "--format=", entry.commit)).splitlines()
    patch = [f"{COMMIT_MARK}{entry.commit}", *patch]
    flagged = {(hit["file"].removeprefix("b/"), hit["context"]) for hit in scan_credentials(patch)}
    for _commit, file, content in added_lines(patch):
        if file.removeprefix("b/") == entry.file and line_digest(content) == entry.line_digest:
            if (entry.file, content.strip()[:160]) in flagged:
                return None
            return f"{label}: the pinned line no longer matches the secret scanner; delete this entry"
    return f"{label}: the commit does not add the pinned line to {entry.file}"
