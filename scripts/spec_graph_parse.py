"""Per-file-type dependency-edge and size-signal extraction.

Each ``_apply_*`` handler reads one spec file's text and folds what it finds
into the already-loaded ``Requirement`` objects: see
``plans/refactor/reconciliation-20261006/SPEC-SIZING-AND-DEPENDENCIES.md``
section 1 for the dependency rule this implements.
"""

from __future__ import annotations

import re

if __package__:
    from .spec_graph_core import Requirement, add_edge, apply_signals, find_ids
else:
    from spec_graph_core import Requirement, add_edge, apply_signals, find_ids

TASK_LINE = re.compile(r"^-\s\[([ xX])\]\s*(.*)$")
BOLD_SPAN = re.compile(r"\*\*([^*]+)\*\*")
HEADING = re.compile(r"^#{1,6}\s")
HEADING_WITH_IDS = re.compile(r"^#{1,6}\s+.*\(([^)]*)\)\s*$")


def parse_requirements_md(text: str) -> dict[str, tuple[str, str]]:
    """Map requirement ID -> (requirement text, verification text) from the table."""
    rows: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        if len(cells) < 3:
            continue
        match = re.fullmatch(r"`([^`]+)`", cells[0])
        if match:
            rows[match.group(1)] = (cells[1], cells[2])
    return rows


def _apply_requirements_md(text: str, reqs: dict[str, Requirement]) -> None:
    """A table row names its own ID's dependencies: the row's own ID depends on
    every other requirement ID its requirement/verification text names."""
    for rid, (requirement_text, verification_text) in parse_requirements_md(
        text
    ).items():
        req = reqs.get(rid)
        if req is None:
            continue
        block = f"{requirement_text} {verification_text}"
        add_edge(req, find_ids(block), reqs)
        apply_signals(req, block)


def _task_primaries(content: str) -> set[str]:
    """The bold-marked ``**ID**``/``**ID1, ID2**`` requirement IDs on a task line."""
    primaries: set[str] = set()
    for bold in BOLD_SPAN.finditer(content):
        primaries |= find_ids(bold.group(1))
    return primaries


def _record_task_line(
    content: str, checked: bool, reqs: dict[str, Requirement]
) -> None:
    ids_here = find_ids(content)
    if not checked:
        for rid in ids_here:
            if rid in reqs:
                reqs[rid].unchecked_tasks += 1
    primaries = _task_primaries(content)
    other = ids_here - primaries
    for rid in primaries:
        req = reqs.get(rid)
        if req is not None:
            add_edge(req, other, reqs)
            apply_signals(req, content)


def _apply_tasks_md(text: str, reqs: dict[str, Requirement]) -> None:
    """A task line names its own bold-marked ID(s)' dependencies: a bold-marked
    ID on the line depends on every other requirement ID the line names, and
    every ID the line names gets one unchecked-task point when unchecked."""
    for line in text.splitlines():
        match = TASK_LINE.match(line.strip())
        if match:
            _record_task_line(match.group(2), match.group(1).lower() == "x", reqs)


def _heading_sections(text: str) -> list[tuple[set[str], str]]:
    """Body text under each ``### Title (ID1, ID2)``-style heading, keyed by
    the IDs the heading itself names. A heading without a parenthetical ID
    list (for example a plain ``## Acceptance boundary``) owns no section."""
    sections: list[tuple[set[str], str]] = []
    current_ids: set[str] = set()
    buffer: list[str] = []

    def flush() -> None:
        if current_ids:
            sections.append((current_ids, "\n".join(buffer)))

    for line in text.splitlines():
        if HEADING.match(line):
            flush()
            buffer = []
            heading_match = HEADING_WITH_IDS.match(line.strip())
            current_ids = find_ids(heading_match.group(1)) if heading_match else set()
            continue
        buffer.append(line)
    flush()
    return sections


def _apply_spec_md(text: str, reqs: dict[str, Requirement]) -> None:
    """Every paragraph's requirement mentions accumulate size signals (code
    roots, other repositories); only an ``(ID list)`` heading's body also adds
    dependency edges, since a plain prose list grouping many IDs by theme is a
    classification, not a prerequisite order."""
    for paragraph in re.split(r"\n\s*\n", text):
        for rid in find_ids(paragraph):
            if rid in reqs:
                apply_signals(reqs[rid], paragraph)
    for heading_ids, body in _heading_sections(text):
        other = find_ids(body) - heading_ids
        for rid in heading_ids:
            req = reqs.get(rid)
            if req is not None:
                add_edge(req, other, reqs)
                apply_signals(req, body)


def _apply_test_spec_md(text: str, reqs: dict[str, Requirement]) -> None:
    """Each paragraph that names a requirement counts as one of its distinct
    acceptance/verification clauses, beyond the one already on its
    requirements.md row."""
    for paragraph in re.split(r"\n\s*\n", text):
        for rid in find_ids(paragraph):
            req = reqs.get(rid)
            if req is not None:
                req.test_mentions += 1
                apply_signals(req, paragraph)


FILE_HANDLERS = {
    "requirements.md": _apply_requirements_md,
    "tasks.md": _apply_tasks_md,
    "spec.md": _apply_spec_md,
    "test-spec.md": _apply_test_spec_md,
}
