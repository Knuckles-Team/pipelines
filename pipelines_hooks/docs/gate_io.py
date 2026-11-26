"""Shared plumbing of the declared documentation gates: snapshot reads, findings, evidence lines.

Every declared gate reads its declaration and subjects from the staged Git snapshot,
collects located findings (exit 1) and raises :class:`CannotRun` (exit 2) when it
cannot produce a trustworthy verdict.  Nothing here imports or executes repository code.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes

_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "null": (type(None),),
}


@dataclass
class Result:
    """Findings (exit 1) plus the evidence lines every run prints."""

    findings: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def exit_code(self) -> int:
        return 1 if self.findings else 0


def sha(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()[:16]


def safe_path(gate: str, path: str) -> str:
    pure = PurePosixPath(path)
    if not path or pure.is_absolute() or ".." in pure.parts or "\\" in path:
        raise CannotRun(f"{gate}: unsafe repository path {path!r}")
    return path


def read(root: Path, path: str) -> bytes | None:
    return blob_bytes(root, f":{path}")


def require(gate: str, root: Path, path: str) -> bytes:
    raw = read(root, safe_path(gate, path))
    if raw is None:
        raise CannotRun(f"{gate}: {path} is not in the staged snapshot")
    return raw


def load_json(gate: str, root: Path, path: str) -> tuple[Any, bytes]:
    raw = require(gate, root, path)
    try:
        return json.loads(raw.decode("utf-8")), raw
    except (UnicodeError, ValueError) as exc:
        raise CannotRun(f"{gate}: {path} is unreadable: {exc}") from exc


def line_of(text: str, needle: str) -> int:
    index = text.find(needle)
    return text[:index].count("\n") + 1 if index >= 0 else 1


def type_ok(value: object, declared: str) -> bool:
    expected = _TYPES.get(declared)
    if expected is None:
        raise CannotRun(f"unsupported schema type {declared!r}")
    if isinstance(value, bool) and declared in {"integer", "number"}:
        return False
    return isinstance(value, expected)


def strict_keys(
    gate: str, where: str, data: object, allowed: set[str], required: set[str] | None = None
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise CannotRun(f"{gate}: {where} must be an object")
    unknown = set(data) - allowed
    if unknown:
        raise CannotRun(f"{gate}: {where} has unknown fields {sorted(unknown)}")
    missing = (required or set()) - set(data)
    if missing:
        raise CannotRun(f"{gate}: {where} lacks {sorted(missing)}")
    return data


def finish(gate: str, title: str, result: Result) -> int:
    for line in result.lines:
        print(line)
    if not result.findings:
        print(f"{title}: clean")
        return 0
    print(f"FAIL: {title}.")
    for finding in result.findings:
        print(f"  - {finding}")
    return 1


def fenced_blocks(text: str) -> list[tuple[int, str, str]]:
    """``(line, info, body)`` of each fenced code block."""
    return [
        (text[: m.start()].count("\n") + 1, m["info"], m["body"])
        for m in re.finditer(r"^```(?P<info>[^\n]*)\n(?P<body>.*?)^```", text, re.S | re.M)
    ]
