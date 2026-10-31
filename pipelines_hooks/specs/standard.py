"""spec-standard: every ``specs/<dir>/`` follows the spec standard (reference/spec-standard.md).

Checks per spec directory: file set, title line, spec ID shape, forbidden name words,
and the ``specs/README.md`` index entry. Across every authored ``specs/**/*.md`` file:
no third-party product or project names (``third_party_names.toml``). The narrative,
task-line and status-header rules (``narrative.py``) fail for a touched file and are advisory
for an untouched one. No baseline and no suppression.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.specs import narrative
from pipelines_hooks.specs.requirements_doc import parse_rows
from pipelines_hooks.specs.third_party_names import check_repository

REQUIRED = (
    "spec.md",
    "plan.md",
    "requirements.md",
    "tasks.md",
    "test-spec.md",
)
FORBIDDEN = ("design.md", "architecture.md", "coverage.md", "cross-repo.md")
BAD_WORDS = {"audit", "review", "gap", "carryover", "followup", "fix"}
TITLE_RE = re.compile(r"^# ([A-Z0-9]+(?:-[A-Z0-9]+)*) — \S.*$")
SUFFIX_RE = re.compile(r"-\d+$")

#: The one row ID shape: `<PREFIX>-R<nnn>` with optional `.n` children (reference/spec-standard.md).
ROW_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*-R[0-9]{3}(\.[0-9]+)*$")

#: The ID in the first cell of a requirements.md table row, whatever its shape.
FIRST_CELL_RE = re.compile(r"^\|\s*`([^`\s|]+)`\s*\|", re.M)

#: Advisory until every repository has deleted its tombstone rows; `--tombstones` enforces it.
TOMBSTONE = "is a tombstone for a moved row"

#: Marks a finding that fails only for a touched file and is advisory otherwise.
ADVISORY_TAG = " (advisory: spec not touched)"
#: Advisory for every repository until each one carries its constitution.
CONSTITUTION_MARK = "constitution.md is missing"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def check_files(spec_dir: Path) -> list[str]:
    """Missing required files and present forbidden files."""
    out = [f"missing required file {n}" for n in REQUIRED if not (spec_dir / n).is_file()]
    out += [f"forbidden file {n}" for n in FORBIDDEN if (spec_dir / n).exists()]
    return out


def check_title(spec_dir: Path) -> tuple[str | None, list[str]]:
    """The spec ID parsed from line 1 of spec.md, plus any title finding."""
    lines = _read(spec_dir / "spec.md").splitlines()
    match = TITLE_RE.match(lines[0]) if lines else None
    if not match:
        return None, ["spec.md line 1 must match '# <ID> — <Title>'"]
    return match.group(1), []


def check_id(spec_dir: Path, spec_id: str) -> list[str]:
    """No numeric suffix; every active row ID matches ``ROW_ID_RE`` and starts with ``<ID>-R``.

    Retired rows retain their original IDs when moved between owning specs, so they are exempt.
    """
    out = []
    if SUFFIX_RE.search(spec_id):
        out.append(f"spec ID {spec_id} has a numeric suffix")
    text = _read(spec_dir / "requirements.md")
    retired = {row.id for row in parse_rows(text) if row.retired_reason is not None}
    for rid in dict.fromkeys(FIRST_CELL_RE.findall(text)):
        if rid in retired:
            continue
        if not ROW_ID_RE.match(rid):
            out.append(f"requirements.md row {rid} does not match <PREFIX>-R<nnn>[.n] ({ROW_ID_RE.pattern})")
        elif not rid.startswith(spec_id + "-R"):
            out.append(f"requirements.md row {rid} does not start with {spec_id}-R")
    return out


def check_tombstones(spec_dir: Path) -> list[str]:
    """A ``RETIRED: replaced by`` row is a tombstone for a moved row."""
    rows = parse_rows(_read(spec_dir / "requirements.md"))
    return [
        f"requirements.md row {r.id} {TOMBSTONE}; delete it"
        for r in rows
        if (r.retired_reason or "").startswith("replaced by")
    ]


def check_names(name: str, spec_id: str | None) -> list[str]:
    """Forbidden words as hyphen-separated tokens in the directory name or ID."""
    out = []
    for label, value in (("directory name", name), ("spec ID", spec_id)):
        tokens = set((value or "").lower().split("-"))
        out += [f"{label} contains forbidden word '{w}'" for w in sorted(tokens & BAD_WORDS)]
    return out


def check_touched_rules(spec_dir: Path, root: Path | None, touched: set[str]) -> list[str]:
    """Narrative, task-line and status-header findings; untouched files get ``ADVISORY_TAG``."""
    texts = {n: _read(spec_dir / n) for n in ("spec.md", "plan.md", "requirements.md", "tasks.md", "test-spec.md")}
    base = root or spec_dir.parent.parent

    def tag(name: str, items: list[str]) -> list[str]:
        if narrative.is_touched(touched, spec_dir, base, name):
            return items
        return [i + ADVISORY_TAG for i in items]

    out = tag("spec.md", narrative.check_narrative(texts["spec.md"], texts["requirements.md"]))
    out += tag("tasks.md", narrative.check_tasks(texts["tasks.md"], texts["requirements.md"]))
    status = narrative.check_status_header(texts)
    out += [
        m + ("" if narrative.is_touched(touched, spec_dir, base, m.split(":")[0]) else ADVISORY_TAG) for m in status
    ]
    return out


def check_spec(spec_dir: Path, index: str, touched: set[str] | None = None, root: Path | None = None) -> list[str]:
    """Findings for one spec directory, as ``(path, message)``-joined lines."""
    spec_id, title = check_title(spec_dir)
    found = [*check_files(spec_dir), *title, *narrative.check_optional(spec_dir)]
    texts = {n: _read(spec_dir / n) for n in ("spec.md", "requirements.md")}
    found += narrative.check_markers(spec_dir, texts)
    found += check_touched_rules(spec_dir, root, touched or set())
    if spec_id:
        found += check_id(spec_dir, spec_id)
    found += check_tombstones(spec_dir)
    found += check_names(spec_dir.name, spec_id)
    if f"]({spec_dir.name}/spec.md)" not in index:
        found.append("not listed in specs/README.md")
    return [f"spec-standard: specs/{spec_dir.name}: {m}" for m in found]


def _spec_dirs(root: Path) -> list[Path]:
    return [
        d
        for d in sorted((root / "specs").glob("*/"))
        if d.is_dir() and d.name != "_template" and ((d / "spec.md").is_file() or (d / "requirements.md").is_file())
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spec-standard", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--tombstones",
        action="store_true",
        help="fail on a tombstone row for a moved requirement (advisory by default)",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="revision the change is measured against (default: the pushed-over ref, then origin/main)",
    )
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    index = _read(root / "specs" / "README.md")
    dirs = _spec_dirs(root)
    touched = narrative.touched_paths(root, args.base)
    found = [f for d in dirs for f in check_spec(d, index, touched, root)]
    if dirs:
        found += [f"spec-standard: {m}" for m in narrative.check_constitution(root)]
    advisory = (ADVISORY_TAG, CONSTITUTION_MARK) + (() if args.tombstones else (TOMBSTONE,))
    findings = [f for f in found if not any(mark in f for mark in advisory)]
    if (root / "specs").is_dir():
        named = check_repository(root)
        found += named
        findings += named
    for finding in found:
        print(finding if finding in findings else f"ADV {finding}")
    if findings:
        print(f"spec-standard: FAIL: {len(findings)} finding(s)")
        return 1
    print(f"spec-standard: clean ({len(dirs)} spec(s) checked)")
    return 0
