"""The reviewed register of dupehound pairs that are NOT clones (``.config/dupehound-distinct.toml``).

A baseline is machine-written, unexplained and grows by default. This register
is HAND-WRITTEN, carries a reason per entry, and ROTS: every entry pins the
normalized text of BOTH functions, so changing either brings the finding back
for re-review, and an entry whose functions changed or vanished fails the gate.
Nothing here updates itself. A repository without the file has no entries.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from pipelines_hooks.clones.ledger_text import delegates_to, digest_of, function_exists, normalized_function_text
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.layout import DUPEHOUND_DISTINCT, located

REGISTER = DUPEHOUND_DISTINCT
_FIELDS = ("left_file", "left_name", "left_digest", "right_file", "right_name", "right_digest", "reason", "reviewed_on")


class PairKey(NamedTuple):
    file: str
    name: str
    other_file: str
    other_name: str

    def reversed(self) -> PairKey:
        return PairKey(self.other_file, self.other_name, self.file, self.name)


@dataclass(frozen=True)
class DistinctPair:
    left_file: str
    left_name: str
    left_digest: str
    right_file: str
    right_name: str
    right_digest: str
    reason: str
    reviewed_on: str

    def key(self) -> PairKey:
        return PairKey(self.left_file, self.left_name, self.right_file, self.right_name)


def _pair(index: int, entry: object) -> DistinctPair:
    if not isinstance(entry, dict) or any(not isinstance(entry.get(f), str) or not entry[f].strip() for f in _FIELDS):
        raise CannotRun(f"{REGISTER} entry {index} must set every field: {', '.join(_FIELDS)}")
    if len(entry["reason"].split()) < 12:
        raise CannotRun(f"{REGISTER} entry {index} has no real justification (a reviewed claim says WHY)")
    return DistinctPair(**{field: entry[field] for field in _FIELDS})


def load_register(root: Path) -> list[DistinctPair]:
    path = located(root, REGISTER)
    if not path.exists():
        return []
    try:
        entries = tomllib.loads(path.read_text(encoding="utf-8")).get("pair", [])
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"{REGISTER} is unreadable: {exc}") from exc
    if not isinstance(entries, list):
        raise CannotRun(f"{REGISTER}: `pair` must be an array of tables")
    return [_pair(index, entry) for index, entry in enumerate(entries)]


def resolved_reason(finding: dict[str, Any], root: Path) -> str | None:
    """Why a finding names no duplication that exists any more, or ``None``."""
    file, original = root / finding["file"], root / finding["original_file"]
    name, original_name = finding["name"], finding["original_name"]
    if not function_exists(original, original_name):
        return f"{finding['original_file']}::{original_name} is no longer in the tree"
    if not function_exists(file, name):
        return f"{finding['file']}::{name} is no longer in the tree"
    if delegates_to(file, finding["line"], (name, original_name)):
        return f"{name} delegates to {original_name} rather than reimplementing it"
    if delegates_to(original, finding["original_line"], (original_name, name)):
        return f"{original_name} delegates to {name} rather than reimplementing it"
    return None


def rot_note(pair: DistinctPair, root: Path) -> str | None:
    """Why a register entry no longer describes its code, or ``None`` if it holds."""
    left = normalized_function_text(root / pair.left_file, 1, pair.left_name)
    right = normalized_function_text(root / pair.right_file, 1, pair.right_name)
    label = f"{pair.left_file}::{pair.left_name} / {pair.right_file}::{pair.right_name}"
    if left is None or right is None:
        return f"{label}: a reviewed function no longer exists -- delete this entry"
    if digest_of(left) != pair.left_digest or digest_of(right) != pair.right_digest:
        return f"{label}: reviewed {pair.reviewed_on}, source changed since -- re-review or consolidate"
    return None


def _classify(finding: dict[str, Any], by_key: dict[PairKey, DistinctPair], root: Path) -> tuple[str | None, str | None]:
    """``(bucket, note)``: bucket is ``unregistered``, ``changed`` or ``None``."""
    resolved = resolved_reason(finding, root)
    if resolved is not None:
        return None, f"resolved: {finding['file']}:{finding['line']} {finding['name']} -- {resolved}"
    key = PairKey(finding["file"], finding["name"], finding["original_file"], finding["original_name"])
    pair = by_key.get(key) or by_key.get(key.reversed())
    if pair is None:
        return "unregistered", None
    note = rot_note(pair, root)
    return ("changed" if note else None), note


def partition(findings: list[dict[str, Any]], pairs: list[DistinctPair], root: Path) -> dict[str, list[Any]]:
    """Split into ``unregistered`` failures, ``changed`` pairs, ``notes`` and ``rotted`` entries."""
    by_key = {pair.key(): pair for pair in pairs}
    result: dict[str, list[Any]] = {"unregistered": [], "changed": [], "notes": [], "rotted": []}
    for finding in findings:
        bucket, note = _classify(finding, by_key, root)
        if bucket:
            result[bucket].append(finding)
        if note:
            result["notes"].append(note)
    for pair in pairs:
        note = rot_note(pair, root)
        if note:
            result["rotted"].append(pair)
            result["notes"].append(note)
    return result
