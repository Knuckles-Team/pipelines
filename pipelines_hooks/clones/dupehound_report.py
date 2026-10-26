"""Validate dupehound's versioned JSON findings payload."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pipelines_hooks.clones.contract import DUPEHOUND_DIAGNOSTIC_THRESHOLD, DUPEHOUND_THRESHOLD
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.paths import relative_to_root

SCHEMA_VERSION = 1
SCANNER_IDENTITY = "dupehound 0.1.2"
REQUIRED_FIELDS = ("file", "line", "name", "similarity", "original_file", "original_line", "original_name")
#: dupehound 0.1.2 ignores ``--json`` when its own change detection finds
#: nothing: it prints this line and exits 0.
NO_CHANGES_SENTINEL = "dupehound check: no changes to check"


@dataclass(frozen=True)
class SimilarityReport:
    """One validated clone pair with the evidence needed for review."""

    file: str
    line: int
    name: str
    original_file: str
    original_line: int
    original_name: str
    similarity: float
    source_digest: str
    original_source_digest: str
    scanner: str
    diagnostic_threshold: float
    enforcement_threshold: float
    disposition: Literal["below-diagnostic", "diagnostic", "enforcement"]
    advice: str

    @property
    def finding(self) -> dict[str, Any]:
        """The scanner finding in the shape expected by the reviewed register."""
        return {
            "file": self.file,
            "line": self.line,
            "name": self.name,
            "original_file": self.original_file,
            "original_line": self.original_line,
            "original_name": self.original_name,
            "similarity": self.similarity,
        }

    def as_dict(self) -> dict[str, object]:
        """Stable evidence fields for a human or a downstream receipt."""
        return {
            "file": self.file,
            "line": self.line,
            "name": self.name,
            "original_file": self.original_file,
            "original_line": self.original_line,
            "original_name": self.original_name,
            "similarity": self.similarity,
            "source_digest": self.source_digest,
            "original_source_digest": self.original_source_digest,
            "scanner": self.scanner,
            "diagnostic_threshold": self.diagnostic_threshold,
            "enforcement_threshold": self.enforcement_threshold,
            "disposition": self.disposition,
            "verdict": self.disposition,
            "advice": self.advice,
        }


def validate_thresholds(diagnostic: float, enforcement: float) -> None:
    """Reject thresholds that would make diagnostic evidence outrank enforcement."""
    values = (diagnostic, enforcement)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise CannotRun("dupehound thresholds must be finite numbers")
    if any(not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0 for value in values):
        raise CannotRun("dupehound thresholds must be between 0 and 1")
    if float(diagnostic) > float(enforcement):
        raise CannotRun("dupehound diagnostic threshold cannot exceed enforcement threshold")


def _source_digest(root: Path, relative: str) -> str:
    """Digest the complete source file named by a scanner finding."""
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise CannotRun(f"dupehound finding names an unreadable source file: {relative}")
    try:
        payload = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"dupehound finding source cannot be read: {relative}: {exc}") from exc
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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
    context = (
        f" (dupehound exited {result.returncode}; stderr: {stderr[:300]})" if stderr else f" (exit {result.returncode})"
    )
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


def _disposition(
    similarity: float, diagnostic: float, enforcement: float
) -> Literal["below-diagnostic", "diagnostic", "enforcement"]:
    if similarity < diagnostic:
        return "below-diagnostic"
    if similarity < enforcement:
        return "diagnostic"
    return "enforcement"


def reports(
    result: subprocess.CompletedProcess[str],
    root: Path,
    *,
    diagnostic: float = DUPEHOUND_DIAGNOSTIC_THRESHOLD,
    enforcement: float = DUPEHOUND_THRESHOLD,
    scanner: str = SCANNER_IDENTITY,
) -> list[SimilarityReport]:
    """Build digest-bound review reports from one validated scanner result."""
    validate_thresholds(diagnostic, enforcement)
    validated = findings(result, root)
    output: list[SimilarityReport] = []
    for finding in validated:
        similarity = float(finding["similarity"])
        output.append(
            SimilarityReport(
                file=finding["file"],
                line=finding["line"],
                name=finding["name"],
                original_file=finding["original_file"],
                original_line=finding["original_line"],
                original_name=finding["original_name"],
                similarity=similarity,
                source_digest=_source_digest(root, finding["file"]),
                original_source_digest=_source_digest(root, finding["original_file"]),
                scanner=scanner,
                diagnostic_threshold=float(diagnostic),
                enforcement_threshold=float(enforcement),
                disposition=_disposition(similarity, float(diagnostic), float(enforcement)),
                advice=("review the pair and consider extracting a shared function; do not rewrite without review"),
            )
        )
    return output


def partition_reports(
    reports_: list[SimilarityReport],
) -> tuple[list[SimilarityReport], list[SimilarityReport], list[SimilarityReport]]:
    """Return ``(ignored, diagnostic, enforcement)`` reports in input order."""
    ignored: list[SimilarityReport] = []
    diagnostic: list[SimilarityReport] = []
    enforcement: list[SimilarityReport] = []
    for report in reports_:
        if report.disposition == "below-diagnostic":
            ignored.append(report)
        elif report.disposition == "diagnostic":
            diagnostic.append(report)
        else:
            enforcement.append(report)
    return ignored, diagnostic, enforcement
