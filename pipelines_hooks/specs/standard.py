"""spec-standard: every ``specs/<dir>/`` follows the spec standard (reference/spec-standard.md).

Checks per spec directory: file set, title line, spec ID shape, forbidden name words,
and the ``specs/README.md`` index entry. No baseline and no suppression.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.specs.requirements_doc import parse_rows

REQUIRED = (
    "spec.md",
    "plan.md",
    "requirements.md",
    "tasks.md",
    "test-spec.md",
    "status.json",
)
FORBIDDEN = ("design.md", "architecture.md", "coverage.md", "cross-repo.md")
BAD_WORDS = {"audit", "review", "gap", "carryover", "followup", "fix"}
TITLE_RE = re.compile(r"^# ([A-Z0-9]+(?:-[A-Z0-9]+)*) — \S.*$")
SUFFIX_RE = re.compile(r"-\d+$")

#: A row ID in the standard form; older forms keep their permanent IDs.
STANDARD_ROW_RE = re.compile(r"-R\d{3}(?:\.\d+)*$")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def check_files(spec_dir: Path) -> list[str]:
    """Missing required files and present forbidden files."""
    out = [
        f"missing required file {n}" for n in REQUIRED if not (spec_dir / n).is_file()
    ]
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
    """No numeric suffix; every ``-R###`` row ID starts with ``<ID>-R``.

    A row ID in an older form (``DS-01``) is permanent and is not a finding.
    Retired rows retain their original IDs when moved between owning specs.
    """
    out = []
    if SUFFIX_RE.search(spec_id):
        out.append(f"spec ID {spec_id} has a numeric suffix")
    rows = (row for line in _read(spec_dir / "requirements.md").splitlines()
            for row in parse_rows(line))
    for row in rows:
        if (
            row.retired_reason is None
            and STANDARD_ROW_RE.search(row.id)
            and not row.id.startswith(spec_id + "-R")
        ):
            out.append(
                f"requirements.md row {row.id} does not start with {spec_id}-R"
            )
    return out


def check_names(name: str, spec_id: str | None) -> list[str]:
    """Forbidden words as hyphen-separated tokens in the directory name or ID."""
    out = []
    for label, value in (("directory name", name), ("spec ID", spec_id)):
        tokens = set((value or "").lower().split("-"))
        out += [
            f"{label} contains forbidden word '{w}'" for w in sorted(tokens & BAD_WORDS)
        ]
    return out


def check_spec(spec_dir: Path, index: str) -> list[str]:
    """Findings for one spec directory, as ``(path, message)``-joined lines."""
    spec_id, title = check_title(spec_dir)
    found = [*check_files(spec_dir), *title]
    if spec_id:
        found += check_id(spec_dir, spec_id)
    found += check_names(spec_dir.name, spec_id)
    if f"]({spec_dir.name}/spec.md)" not in index:
        found.append("not listed in specs/README.md")
    return [f"spec-standard: specs/{spec_dir.name}: {m}" for m in found]


def _spec_dirs(root: Path) -> list[Path]:
    return [
        d
        for d in sorted((root / "specs").glob("*/"))
        if d.is_dir()
        and d.name != "_template"
        and ((d / "spec.md").is_file() or (d / "status.json").is_file())
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spec-standard", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    index = _read(root / "specs" / "README.md")
    dirs = _spec_dirs(root)
    findings = [f for d in dirs for f in check_spec(d, index)]
    for finding in findings:
        print(finding)
    if findings:
        print(f"spec-standard: FAIL: {len(findings)} finding(s)")
        return 1
    print(f"spec-standard: clean ({len(dirs)} spec(s) checked)")
    return 0
