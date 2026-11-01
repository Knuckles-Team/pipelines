"""spec-standard narrative checks: the optional artifacts, the constitution, the ``spec.md``
sections, the clarification marker, the task line and the no-status rule.

Rules that need a rewrite of an older spec (narrative sections, task line, status header)
fail for a spec the change touches and are advisory for any other spec. See
reference/spec-standard.md "The gate".
"""

from __future__ import annotations

import re
from pathlib import Path

from pipelines_hooks.core.baseref import upstream_base
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, nul_split, staged_paths

#: Upstream optional artifacts. Files, then directories.
OPTIONAL_FILES = ("research.md", "data-model.md", "quickstart.md")
OPTIONAL_DIRS = ("contracts", "checklists")

CONSTITUTION = Path(".specify") / "memory" / "constitution.md"

MARKER_RE = re.compile(r"\[NEEDS CLARIFICATION:[^\]]*\]")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_RE = re.compile(r"`[^`\n]*`")
ROW_TOKEN = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R\d{3}(?:\.\d+)*"
ROW_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9-])(" + ROW_TOKEN + r")(?![0-9A-Za-z])")
STORY_RE = re.compile(r"^#{2,4}\s+User Story\s+\d+\b.*\(Priority:\s*P\d+\)", re.M)
SCENARIO_RE = re.compile(r"\bGiven\b.*\bWhen\b.*\bThen\b", re.I)
LABEL_RE = re.compile(r"^\s*[-*]\s+(?:\*\*)?((?:FR|SC)-\d+)\b")
TASK_BOX_RE = re.compile(r"^\s*- \[[ xX]\]\s")
TASK_RE = re.compile(r"^- \[[ xX]\] T\d{3,}(?: \[P\])?(?: \[US\d+\])? (" + ROW_TOKEN + r") \S")
STATUS_RE = re.compile(r"^\s*(?:\*\*)?Status(?:\*\*)?\s*:", re.I | re.M)
FIRST_CELL_RE = re.compile(r"^\|\s*`([^`\s|]+)`\s*\|", re.M)


def prose(text: str) -> list[tuple[int, str]]:
    """``(line number, line)`` outside fenced code, with inline code spans blanked."""
    out, fenced = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            out.append((number, INLINE_RE.sub("", line)))
    return out


def check_optional(spec_dir: Path) -> list[str]:
    """An optional artifact must be the right kind: a file, or a directory."""
    out = [f"{n} must be a file" for n in OPTIONAL_FILES if (spec_dir / n).is_dir()]
    out += [
        f"{n}/ must be a directory" for n in OPTIONAL_DIRS if (spec_dir / n).exists() and not (spec_dir / n).is_dir()
    ]
    return out


def check_constitution(root: Path) -> list[str]:
    """A repository with specs holds the one-page constitution (advisory)."""
    if (root / CONSTITUTION).is_file():
        return []
    return [f"{CONSTITUTION.as_posix()} is missing; copy .specify/templates/constitution-template.md"]


def check_markers(spec_dir: Path, texts: dict[str, str]) -> list[str]:
    """An open clarification marker in ``spec.md`` or ``requirements.md``."""
    out = []
    for name in ("spec.md", "requirements.md"):
        for number, line in prose(texts.get(name, "")):
            if MARKER_RE.search(line):
                out.append(f"{name}:{number} holds an open [NEEDS CLARIFICATION: ...] marker; resolve it")
    return out


def check_status_header(texts: dict[str, str]) -> list[str]:
    """No written state: the generator computes it."""
    out = []
    for name in ("spec.md", "plan.md", "tasks.md", "test-spec.md"):
        for number, line in prose(texts.get(name, "")):
            if STATUS_RE.match(line):
                out.append(f"{name}:{number} writes a Status line; state is computed, delete it")
    return out


def _row_ids(requirements: str) -> set[str]:
    return set(FIRST_CELL_RE.findall(requirements))


def check_narrative(spec_md: str, requirements: str) -> list[str]:
    """Prioritized stories, Given/When/Then, Edge Cases, Assumptions, and labelled rows."""
    out = []
    lines = prose(spec_md)
    body = "\n".join(line for _, line in lines)
    if not STORY_RE.search(body):
        out.append("spec.md holds no '### User Story N - <title> (Priority: P1)' heading")
    if not any(SCENARIO_RE.search(line) for _, line in lines):
        out.append("spec.md holds no Given/When/Then acceptance scenario")
    for section in ("Edge Cases", "Assumptions"):
        if not re.search(rf"^#{{2,4}}\s+{section}\s*$", body, re.M):
            out.append(f"spec.md has no '{section}' section")
    known = _row_ids(requirements)
    for number, raw in enumerate(spec_md.splitlines(), 1):
        match = LABEL_RE.match(raw)
        if not match:
            continue
        label = match.group(1)
        named = ROW_TOKEN_RE.findall(raw)
        if not named:
            out.append(f"spec.md:{number} {label} names no -R row")
        out += [f"spec.md:{number} {label} names {r}, which requirements.md lacks" for r in named if r not in known]
    return out


def check_tasks(tasks: str, requirements: str) -> list[str]:
    """Every task line is ``- [ ] T001 [P] [US1] <ID>-R012.4 description`` naming an existing row."""
    out, known = [], _row_ids(requirements)
    for number, line in prose(tasks):
        if not TASK_BOX_RE.match(line):
            continue
        match = TASK_RE.match(line)
        if not match:
            out.append(f"tasks.md:{number} must read '- [ ] T001 [P] [US1] <ID>-R012.4 description'")
        elif match.group(1) not in known:
            out.append(f"tasks.md:{number} names {match.group(1)}, which requirements.md lacks")
    return out


def touched_paths(root: Path, base: str | None = None) -> set[str]:
    """Paths the change touches: staged, plus the diff of the working tree against the base."""
    touched = set(staged_paths(root))
    try:
        resolved = upstream_base(root, base)
    except CannotRun:
        if base:
            raise
        resolved = None
    if resolved:
        raw = git_text(root, ("diff", "--name-only", "-z", "--diff-filter=ACMR", resolved))
        touched |= set(nul_split(raw))
        raw = git_text(root, ("ls-files", "-z", "--others", "--exclude-standard"))
        touched |= set(nul_split(raw))
    return touched


def is_touched(touched: set[str], spec_dir: Path, root: Path, name: str) -> bool:
    """Whether the change touches ``name`` of this spec (a new spec touches every file)."""
    prefix = spec_dir.resolve().relative_to(root.resolve()).as_posix() + "/"
    return any(p == prefix + name or (name == "" and p.startswith(prefix)) for p in touched)


def added_row_ids(root: Path, spec_dir: Path, touched: set[str], base: str | None = None) -> set[str]:
    """Row IDs on lines the change adds to this spec directory (a whole file when it is new or has no base)."""
    prefix = spec_dir.resolve().relative_to(root.resolve()).as_posix() + "/"
    try:
        resolved = upstream_base(root, base)
    except CannotRun:
        resolved = None
    ids: set[str] = set()
    for path in sorted(p for p in touched if p.startswith(prefix) and p.endswith(".md")):
        text = ""
        in_base = False
        if resolved:
            try:
                git_text(root, ("cat-file", "-e", f"{resolved}:{path}"))
                in_base = True
                diff = git_text(root, ("diff", "-U0", resolved, "--", path))
            except CannotRun:
                diff = ""
            added = (line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
            text = "\n".join(added)
        if not text and not in_base:
            try:
                text = (root / path).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
        ids.update(ROW_TOKEN_RE.findall(text))
    return ids
