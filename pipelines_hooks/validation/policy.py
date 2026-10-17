"""Strict, versioned consumer policy; no executable shell configuration."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

GATES = frozenset({"root-hygiene", "gitignore-convergence", "sprawl"})


@dataclass(frozen=True)
class Check:
    id: str
    group: str
    gate: str
    required: bool
    timeout_seconds: int
    acceptance: list[str]
    remedy: str


@dataclass(frozen=True)
class Policy:
    budget_seconds: int
    checks: list[Check]


def _keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise CannotRun(f"{label}: expected exactly {', '.join(sorted(expected))}")
    return value


def _seconds(value: object, label: str) -> int:
    if type(value) is not int or not 1 <= value <= 300:
        raise CannotRun(f"{label}: expected an integer from 1 to 300")
    return value


def _acceptance(row: dict) -> None:
    acceptance = row["acceptance"]
    if (
        not isinstance(acceptance, list)
        or not acceptance
        or any(not isinstance(item, str) or not item.strip() for item in acceptance)
    ):
        raise CannotRun("each check needs non-empty acceptance identifiers")
    if len(set(acceptance)) != len(acceptance):
        raise CannotRun("acceptance identifiers must be unique within a check")
    if not isinstance(row["remedy"], str) or not row["remedy"].strip():
        raise CannotRun("each check needs an actionable remedy")


def _check(raw: object) -> Check:
    row = _keys(raw, set(Check.__annotations__), "check")
    if not isinstance(row["id"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", row["id"]):
        raise CannotRun("check id must be a stable lowercase name")
    if row["group"] != "repository" or not isinstance(row["gate"], str) or row["gate"] not in GATES:
        raise CannotRun("version 1 supports only the offline repository hygiene gates")
    if type(row["required"]) is not bool:
        raise CannotRun("required must be true or false")
    _seconds(row["timeout_seconds"], "timeout_seconds")
    _acceptance(row)
    return Check(**row)


def load(path: Path) -> Policy:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read validation policy {path}: {exc}") from exc
    document = _keys(raw, {"version", "budget_seconds", "checks"}, "policy")
    if type(document["version"]) is not int or document["version"] != 1:
        raise CannotRun("unsupported validation policy version")
    rows = document["checks"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
        raise CannotRun("version 1 requires one to three unique repository checks")
    checks = [_check(row) for row in rows]
    for field in ("id", "gate"):
        if len({getattr(check, field) for check in checks}) != len(checks):
            raise CannotRun(f"duplicate check {field}; dispatch each acceptance owner once")
    return Policy(_seconds(document["budget_seconds"], "budget_seconds"), checks)
