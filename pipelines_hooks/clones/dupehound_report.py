"""Validate dupehound's versioned JSON findings payload."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.paths import relative_to_root

SCHEMA_VERSION = 1
REQUIRED_FIELDS = ("file", "line", "name", "similarity", "original_file", "original_line", "original_name")
#: dupehound 0.1.2 ignores ``--json`` when its own change detection finds
#: nothing: it prints this line and exits 0.
NO_CHANGES_SENTINEL = "dupehound check: no changes to check"


def _document(output: str, context: str) -> dict[str, Any]:
    stripped = (output or "").strip()
    if stripped == NO_CHANGES_SENTINEL:
        raise CannotRun(
            "dupehound scanned nothing while this gate selected changed source to check"
            f"{context}; its change detection disagreed with the gate's. Nothing was enforced"
        )
    try:
        document = json.loads(output)
    except (TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise CannotRun(f"dupehound returned invalid JSON: {exc}{context}; stdout began {stripped[:200]!r}") from exc
    if not isinstance(document, dict):
        raise CannotRun("dupehound JSON result is not an object")
    return document


def _validate_paths(index: int, finding: dict[str, Any], root: Path) -> None:
    for field in ("file", "original_file"):
        value = finding[field]
        try:
            valid = isinstance(value, str) and bool(relative_to_root(value, root))
        except ValueError:
            valid = False
        if not valid:
            raise CannotRun(f"dupehound finding {index} has an invalid {field}")


def _validate_names_and_lines(index: int, finding: dict[str, Any]) -> None:
    for field in ("name", "original_name"):
        if not isinstance(finding[field], str) or not finding[field].strip():
            raise CannotRun(f"dupehound finding {index} has an invalid {field}")
    for field in ("line", "original_line"):
        value = finding[field]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise CannotRun(f"dupehound finding {index} has an invalid {field}")


def _validate_similarity(index: int, finding: dict[str, Any]) -> None:
    similarity = finding["similarity"]
    if isinstance(similarity, bool) or not isinstance(similarity, (int, float)):
        raise CannotRun(f"dupehound finding {index} has an invalid similarity")
    if not math.isfinite(float(similarity)) or not 0.0 <= float(similarity) <= 1.0:
        raise CannotRun(f"dupehound finding {index} has an invalid similarity")


def validate_finding(index: int, finding: object, root: Path) -> dict[str, Any]:
    if not isinstance(finding, dict):
        raise CannotRun(f"dupehound finding {index} is not an object")
    missing = [field for field in REQUIRED_FIELDS if field not in finding]
    if missing:
        raise CannotRun(f"dupehound finding {index} is missing {', '.join(missing)}")
    _validate_paths(index, finding, root)
    _validate_names_and_lines(index, finding)
    _validate_similarity(index, finding)
    return finding


def findings(result: subprocess.CompletedProcess[str], root: Path) -> list[dict[str, Any]]:
    """Validated findings; exit code, schema and payload must all agree."""
    stderr = (result.stderr or "").strip()
    context = f" (dupehound exited {result.returncode}; stderr: {stderr[:300]})" if stderr else f" (exit {result.returncode})"
    if result.returncode not in (0, 1):
        raise CannotRun(f"dupehound exited {result.returncode}: {stderr[:500]}")
    document = _document(result.stdout or "", context)
    version = document.get("schema_version")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise CannotRun(f"dupehound JSON schema drift: expected {SCHEMA_VERSION}, got {version!r}")
    raw = document.get("findings")
    if not isinstance(raw, list):
        raise CannotRun("dupehound JSON result has no findings array")
    validated = [validate_finding(index, item, root) for index, item in enumerate(raw)]
    if (result.returncode == 1) != bool(validated):
        raise CannotRun(f"dupehound exit {result.returncode} disagrees with {len(validated)} finding(s)")
    return validated
