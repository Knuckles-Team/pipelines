"""export-version: refuse an OWL/RDF workflow import whose export version moved.

A lossless workflow export carries the version it was exported at and the
decision condition (the freshness rule) it was exported under. An import keeps
that condition and compares the exported version with the current one exactly:
an older or newer export, or an export that lost its condition, is refused. No
range, prefix or ordering match is attempted, so no freshness rule is weakened.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun


class Verdict(Enum):
    SAME = "SAME"
    OLDER = "OLDER"
    NEWER = "NEWER"


@dataclass(frozen=True)
class ExportHeader:
    """The two header fields an export must keep for a lossless round trip."""

    exported_version: str
    decision_condition: str


def _release_key(version: str) -> tuple[int, ...] | None:
    parts = version.split(".")
    return tuple(int(part) for part in parts) if all(part.isascii() and part.isdigit() for part in parts) else None


def compare_export_version(header: ExportHeader, current: str) -> Verdict:
    """Exact comparison: equal strings are ``SAME``; anything else is ``OLDER`` or ``NEWER``."""
    if header.exported_version == current:
        return Verdict.SAME
    exported, now = _release_key(header.exported_version), _release_key(current)
    if exported is not None and now is not None and exported > now:
        return Verdict.NEWER
    return Verdict.OLDER if exported is not None and now is not None else Verdict.NEWER


def load_header(path: Path) -> ExportHeader:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRun(f"export-version: cannot read header {path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("exported_version"), str) or not raw["exported_version"]:
        raise CannotRun("export-version: the header needs a non-empty exported_version")
    condition = raw.get("decision_condition")
    return ExportHeader(raw["exported_version"], condition if isinstance(condition, str) else "")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="export-version", description=__doc__)
    parser.add_argument("--header", type=Path, required=True, help="JSON export header")
    parser.add_argument("--current", required=True, help="the current workflow version")
    args = parser.parse_args(argv)
    header = load_header(args.header)
    verdict = compare_export_version(header, args.current)
    print(
        json.dumps(
            {"exported_version": header.exported_version, "current": args.current, "verdict": verdict.value},
            sort_keys=True,
        )
    )
    refused = False
    if not header.decision_condition.strip():
        print("  refused: the export lost its decision condition")
        refused = True
    if verdict is not Verdict.SAME:
        print(f"  refused: export version {header.exported_version} is {verdict.value} than current {args.current}")
        refused = True
    return 1 if refused else 0
