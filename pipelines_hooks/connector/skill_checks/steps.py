"""Skill step and error-recovery linter (US-CONTENT-R010, run by PIPE-GATES-R016.120).

Reads every ``SKILL.md`` under a skills directory. The steps are the numbered items between the markers
``<!-- spec:begin -->`` and ``<!-- spec:end -->``, or under a heading named ``Steps``. Each step states one
objective, one command (an inline or fenced code span) and one verification (a line that says ``verify``).
A skill with at least one step also holds a table with the columns ``Failure``, ``Cause`` and ``Recovery``.
The check has no baseline and no suppression. Output is one ``<path>:<line>: <code>`` line per finding.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

_BEGIN, _END = "<!-- spec:begin -->", "<!-- spec:end -->"
_STEP = re.compile(r"^\s{0,3}(\d+)[.)]\s+(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_CODE = re.compile(r"`[^`\n]+`")
_VERIFY = re.compile(r"\bverif(?:y|ies|ied|ication)\b", re.IGNORECASE)
_MULTI = re.compile(r"(?:;|\band then\b|\bthen\b)\s", re.IGNORECASE)
_VAGUE = re.compile(
    r"^(?:please\s+)?(?:try|retry|rerun|re-run|run)(?:\s+(?:it|the\s+\w+))?(?:\s+again)?$", re.IGNORECASE
)
_COLUMNS = ("failure", "cause", "recovery")


def _split_frontmatter(text: str) -> tuple[int, list[str]]:
    """The 0-based index of the first body line and the body lines."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return index + 1, lines[index + 1 :]
    return 0, lines


def _region(lines: list[str]) -> range | None:
    """Line indexes of the step region: spec markers first, else the ``Steps`` heading section."""
    begin = next((i for i, line in enumerate(lines) if _BEGIN in line), None)
    if begin is not None:
        end = next((i for i in range(begin, len(lines)) if _END in lines[i]), len(lines))
        return range(begin + 1, end)
    for i, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and match.group(2).strip().casefold() == "steps":
            depth = len(match.group(1))
            stop = len(lines)
            for j in range(i + 1, len(lines)):
                nxt = _HEADING.match(lines[j])
                if nxt and len(nxt.group(1)) <= depth:
                    stop = j
                    break
            return range(i + 1, stop)
    return None


def _steps(lines: list[str], region: range) -> Iterator[tuple[int, list[str]]]:
    """Each numbered step as its first line index and its lines (the item and its continuation)."""
    start: int | None = None
    block: list[str] = []
    for i in region:
        if _STEP.match(lines[i]):
            if start is not None:
                yield start, block
            start, block = i, [lines[i]]
        elif start is not None:
            if _HEADING.match(lines[i]):
                yield start, block
                start, block = None, []
            else:
                block.append(lines[i])
    if start is not None:
        yield start, block


def _recovery_cells(lines: list[str]) -> tuple[bool, list[tuple[int, str]]]:
    """Whether the Failure/Cause/Recovery table exists, and its recovery cells with their line indexes."""
    for i, line in enumerate(lines):
        cells = [c.strip().casefold() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and tuple(cells[:3]) == _COLUMNS and len(cells) >= 3:
            found: list[tuple[int, str]] = []
            for j in range(i + 1, len(lines)):
                row = lines[j].strip()
                if not row.startswith("|"):
                    break
                parts = [c.strip() for c in row.strip("|").split("|")]
                if set(row.replace("|", "").strip()) <= set("-: "):
                    continue
                if len(parts) >= 3:
                    found.append((j, parts[2]))
            return True, found
    return False, []


def lint_skill(text: str) -> list[tuple[int, str]]:
    """Findings as ``(1-based line, code)`` for one ``SKILL.md`` text, in line order."""
    offset, lines = _split_frontmatter(text)
    region = _region(lines)
    steps = list(_steps(lines, region)) if region is not None else []
    if not steps:
        return []
    findings: list[tuple[int, str]] = []
    for first, block in steps:
        line = offset + first + 1
        objective = _STEP.match(block[0]).group(2)  # type: ignore[union-attr]
        body = "\n".join(block)
        if _MULTI.search(_CODE.sub("", objective)):
            findings.append((line, "STEP_MULTI_OBJECTIVE"))
        if not _CODE.search(body) and "```" not in body:
            findings.append((line, "STEP_NO_COMMAND"))
        if not _VERIFY.search(body):
            findings.append((line, "STEP_NO_VERIFY"))
    present, cells = _recovery_cells(lines)
    if not present:
        findings.append((offset + steps[0][0] + 1, "RECOVERY_TABLE_MISSING"))
    findings += [(offset + j + 1, "RECOVERY_VAGUE") for j, cell in cells if _VAGUE.match(cell.strip(" .`*"))]
    return sorted(findings)


def lint_tree(skills: Path) -> tuple[list[str], int]:
    """Finding lines for every skill under ``skills`` and the count of unreadable files."""
    out: list[str] = []
    unreadable = 0
    for md in sorted(skills.glob("*/SKILL.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            print(f"{md}: unreadable", file=sys.stderr)
            unreadable += 1
            continue
        out += [f"{md}:{line}: {code}" for line, code in lint_skill(text)]
    return out, unreadable


def main(argv: list[str] | None = None) -> int:
    """Exit 0 when clean, 1 on a finding and 2 when a file cannot be read."""
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[args.index("--root") + 1]) if "--root" in args else Path("universal_skills/skills")
    found, unreadable = lint_tree(root)
    for line in found:
        print(line)
    return 2 if unreadable else (1 if found else 0)


if __name__ == "__main__":
    sys.exit(main())
