"""spec-standard consistency analysis, plan sections and checklist completion.

Cross-file checks over one spec directory: every active row has a task line, every task
names an existing row, every behaviour row has a bound test or a test-spec entry, no
``FR-``/``SC-`` label is orphaned, and no clarification marker is open in the design files.
Also the ``plan.md`` section set and unchecked checklist items. A touched spec fails;
any other spec is advisory (``standard.py`` tags the findings). See
reference/spec-standard.md "Consistency analysis".
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from pipelines_hooks.specs.artifacts import check_artifacts
from pipelines_hooks.specs.narrative import (
    LABEL_RE,
    MARKER_RE,
    ROW_TOKEN_RE,
    TASK_BOX_RE,
    TASK_RE,
    prose,
)
from pipelines_hooks.specs.requirements_doc import Row, parse_rows

#: Upstream plan template sections, then this platform's extensions.
PLAN_SECTIONS = (
    "Summary",
    "Technical Context",
    "Constitution Check",
    "Project Structure",
    "Phase 0",
    "Phase 1",
    "Phase 2",
    "Complexity Tracking",
    "Build contract",
    "Production caller chain",
    "Cross-repo seams",
)
CONTEXT_FIELDS = (
    "Language/Version",
    "Primary Dependencies",
    "Storage",
    "Testing",
    "Target Platform",
    "Project Type",
    "Performance Goals",
    "Constraints",
    "Scale/Scope",
)
LABEL_REF_RE = re.compile(r"(?<![A-Za-z0-9-])((?:FR|SC)-\d+)(?![0-9A-Za-z])")
UNCHECKED_RE = re.compile(r"^\s*- \[ \]\s")
MARKER_FILES = ("plan.md", "tasks.md", "test-spec.md", "research.md", "data-model.md", "quickstart.md")


def active_leaf_rows(rows: Sequence[Row]) -> list[Row]:
    """Rows a task and a test must cover: not retired, and not a rollup of child rows."""
    ids = {r.id for r in rows}
    parents = {r.id.rsplit(".", 1)[0] for r in rows if "." in r.id.rsplit("-R", 1)[-1]}
    return [r for r in rows if r.retired_reason is None and not (r.id in parents and r.id in ids)]


def _labels_by_row(spec_md: str) -> dict[str, set[str]]:
    """Row ID -> labels that map to it."""
    out: dict[str, set[str]] = {}
    for raw in spec_md.splitlines():
        match = LABEL_RE.match(raw)
        if match:
            for row in ROW_TOKEN_RE.findall(raw):
                out.setdefault(row, set()).add(match.group(1))
    return out


def check_tasks_cover_rows(rows: Sequence[Row], tasks: str) -> list[str]:
    """Every active row is named by a task line; a task token naming no row is a finding."""
    out, named, known = [], set(), {r.id for r in rows}
    for number, line in prose(tasks):
        if not TASK_BOX_RE.match(line):
            continue
        match = TASK_RE.match(line)
        if match:
            named.add(match.group(1))
            continue
        out += [
            f"tasks.md:{number} names {t}, which requirements.md lacks"
            for t in ROW_TOKEN_RE.findall(line)
            if t not in known
        ]
    out += [f"tasks.md has no task line for {r.id}" for r in active_leaf_rows(rows) if r.id not in named]
    return out


def check_rows_have_tests(
    rows: Sequence[Row], spec_md: str, test_spec: str, bindings: Mapping[str, object] | None
) -> list[str]:
    """Every behaviour row has a bound test or a test-spec entry (by row ID or by a label that maps to it)."""
    labels = _labels_by_row(spec_md)
    spec_text = test_spec
    out = []
    for row in active_leaf_rows(rows):
        if bindings is not None and bindings.get(row.id):
            continue
        if row.id in ROW_TOKEN_RE.findall(spec_text):
            continue
        if any(re.search(rf"(?<![A-Za-z0-9-]){lab}(?![0-9A-Za-z])", spec_text) for lab in labels.get(row.id, ())):
            continue
        out.append(f"{row.id} has no bound test and no test-spec.md entry")
    return out


def check_labels(spec_md: str, others: Mapping[str, str]) -> list[str]:
    """A label used outside ``spec.md`` must be defined there; a label is defined once."""
    defined: dict[str, int] = {}
    out = []
    for number, raw in enumerate(spec_md.splitlines(), 1):
        match = LABEL_RE.match(raw)
        if not match:
            continue
        label = match.group(1)
        if label in defined:
            out.append(f"spec.md:{number} defines {label} again (first at line {defined[label]})")
        defined.setdefault(label, number)
    for name, text in others.items():
        for number, line in prose(text):
            out += [
                f"{name}:{number} cites {label}, which spec.md does not define"
                for label in dict.fromkeys(LABEL_REF_RE.findall(line))
                if label not in defined
            ]
    return out


def check_open_markers(texts: Mapping[str, str]) -> list[str]:
    """An open clarification marker in a design file (spec.md and requirements.md are checked elsewhere)."""
    return [
        f"{name}:{number} holds an open [NEEDS CLARIFICATION: ...] marker; resolve it"
        for name in MARKER_FILES
        for number, line in prose(texts.get(name, ""))
        if MARKER_RE.search(line)
    ]


def _section(text: str, name: str) -> str | None:
    """Body of the ``## <name>...`` section, or ``None`` when the heading is absent."""
    lines, start = text.splitlines(), None
    for i, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(name)}\b", line, re.I):
            start = i + 1
            break
    if start is None:
        return None
    end = next((j for j in range(start, len(lines)) if lines[j].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def check_plan(plan: str) -> list[str]:
    """``plan.md`` holds the template sections, and Technical Context holds its nine fields."""
    body = "\n".join(line for _, line in prose(plan))
    out = [f"plan.md has no '## {s}' section" for s in PLAN_SECTIONS if _section(body, s) is None]
    context = _section(body, "Technical Context")
    if context is not None:
        low = context.lower()
        out += [f"plan.md Technical Context lacks '{f}'" for f in CONTEXT_FIELDS if f.lower() not in low]
    return out


def check_checklists(spec_dir: Path) -> list[str]:
    """An unchecked item in a requirements-quality checklist blocks landing."""
    out = []
    for path in sorted((spec_dir / "checklists").glob("*.md")) if (spec_dir / "checklists").is_dir() else []:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        out += [
            f"checklists/{path.name}:{n} has an unchecked item" for n, line in prose(text) if UNCHECKED_RE.match(line)
        ]
    return out


def analyze(spec_dir: Path, texts: Mapping[str, str], bindings: Mapping[str, object] | None) -> list[str]:
    """All consistency findings for one spec directory (file-prefixed messages)."""
    rows = parse_rows(texts.get("requirements.md", ""))
    spec_md = texts.get("spec.md", "")
    cited = {n: texts.get(n, "") for n in ("requirements.md", "plan.md", "tasks.md", "test-spec.md")}
    found = check_tasks_cover_rows(rows, texts.get("tasks.md", ""))
    found += check_rows_have_tests(rows, spec_md, texts.get("test-spec.md", ""), bindings)
    found += check_labels(spec_md, cited)
    found += check_open_markers(texts)
    found += check_artifacts(spec_dir, texts)
    return [f"analyze: {m}" for m in found]
