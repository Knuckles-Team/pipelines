"""Validate a complete jscpd v5 JSON report before trusting a single pair."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pipelines_hooks.clones.contract import JSCPD_FORMATS
from pipelines_hooks.clones.jscpd_keys import relative_report_path, report_file_path
from pipelines_hooks.core.errors import CannotRun

REQUIRED_FIELDS = ("format", "fragment", "lines", "tokens", "firstFile", "secondFile")


def _positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _validate_side(index: int, location: object, *, format_name: str, root: Path) -> str:
    if not isinstance(location, dict) or not isinstance(location.get("name"), str) or not location["name"]:
        raise CannotRun(f"jscpd duplicate {index} has an invalid location")
    lines = [location.get(p, {}).get("line") if isinstance(location.get(p), dict) else None for p in ("startLoc", "endLoc")]
    if not all(_positive_int(line) for line in lines) or lines[1] < lines[0]:
        raise CannotRun(f"jscpd duplicate {index} has an invalid or reversed line range")
    name = report_file_path(location["name"], format_name)
    if not Path(name).is_absolute():
        raise CannotRun(f"jscpd duplicate {index} location is not absolute: {name!r}")
    return relative_report_path(name, root)


def _validate_header(index: int, clone: object) -> dict[str, Any]:
    if not isinstance(clone, dict) or any(field not in clone for field in REQUIRED_FIELDS):
        raise CannotRun(f"jscpd duplicate {index} is not a complete object")
    if clone["format"] not in JSCPD_FORMATS:
        raise CannotRun(f"jscpd duplicate {index} has format {clone['format']!r} outside the contract")
    if not isinstance(clone["fragment"], str) or not clone["fragment"].strip():
        raise CannotRun(f"jscpd duplicate {index} has no fragment")
    if not (_positive_int(clone["lines"]) and _positive_int(clone["tokens"])):
        raise CannotRun(f"jscpd duplicate {index} has invalid size fields")
    return clone


def validate_clone(index: int, clone: object, *, root: Path) -> None:
    """One duplicate: fields, format scope, sizes, both locations, and no self-pair."""
    clone = _validate_header(index, clone)
    format_name = clone["format"]
    first = _validate_side(index, clone["firstFile"], format_name=format_name, root=root)
    second = _validate_side(index, clone["secondFile"], format_name=format_name, root=root)
    same_range = all(clone["firstFile"].get(k) == clone["secondFile"].get(k) for k in ("start", "end", "startLoc", "endLoc"))
    if first == second and same_range:
        raise CannotRun(f"jscpd duplicate {index} is a self-pair: both locations name the same range")


def _total(document: dict[str, Any]) -> dict[str, Any]:
    statistics = document.get("statistics")
    total = statistics.get("total") if isinstance(statistics, dict) else None
    if not isinstance(total, dict):
        raise CannotRun("jscpd report has malformed statistics.total")
    for field in ("clones", "sources", "duplicatedLines", "lines"):
        value = total.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CannotRun(f"jscpd report has invalid total.{field}")
    return total


def _validate_total(document: dict[str, Any], count: int) -> None:
    total = _total(document)
    if total["clones"] != count or total["duplicatedLines"] > total["lines"]:
        raise CannotRun("jscpd report totals disagree with its duplicates")
    percentage = total.get("percentage")
    if isinstance(percentage, bool) or not isinstance(percentage, (int, float)) or not math.isfinite(float(percentage)):
        raise CannotRun("jscpd report has invalid total.percentage")


def load_report(report: Path, *, root: Path) -> dict[str, Any]:
    """The validated report written by one jscpd run over ``root``."""
    if report.is_symlink() or not report.is_file():
        raise CannotRun(f"jscpd exited successfully but wrote no report at {report}")
    try:
        document = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CannotRun(f"jscpd report is not valid JSON: {exc}") from exc
    duplicates = document.get("duplicates") if isinstance(document, dict) else None
    if not isinstance(duplicates, list):
        raise CannotRun("jscpd report has no duplicates array")
    _validate_total(document, len(duplicates))
    for index, clone in enumerate(duplicates):
        validate_clone(index, clone, root=root)
    return document
