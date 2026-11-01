"""spec-standard: optional artifacts that must exist where they carry content.

A plan that lists cross-repo seams needs ``contracts/`` with one human-written document per seam.
A spec that adds types, ontology classes or tables needs ``data-model.md``. A spec with a served
behaviour row needs ``quickstart.md``. ``research.md`` exists only when the plan lists unknowns.
``checklists/requirements.md`` exists before landing. See reference/spec-standard.md "Optional artifacts".
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from pipelines_hooks.specs.narrative import FENCE_RE, FIRST_CELL_RE, ROW_TOKEN, ROW_TOKEN_RE, prose

CONTRACT_SECTIONS = ("wire shape", "refusal codes")
PROVIDER_RE = re.compile(r"^Provider: .*" + ROW_TOKEN, re.M)
CONSUMER_RE = re.compile(r"^Consumer: .*" + ROW_TOKEN, re.M)
#: A row adds a type, class or table when a creating verb comes shortly before the noun.
ADDS_RE = re.compile(
    r"\b(?:adds?|introduces?|declares?|defines?|creates?)\b[^|.`]{0,60}?"
    r"\b(?:types?|ontology classes|classes|tables?|entit(?:y|ies))\b",
    re.I,
)
#: A served behaviour row says so in its own text.
SERVED_RE = re.compile(r"\bserved\b|\bhot-path proof\b", re.I)
RUNNER_RE = re.compile(r"\b(?:pytest|cargo|uv run|npm|pnpm|go test|scenario)\b", re.I)
NO_UNKNOWNS_RE = re.compile(r"^\W*(?:no unknowns|none|n/a)\b", re.I)
CODE_RE = re.compile(r"`[^`\n]*`")
CHECKLIST = Path("checklists") / "requirements.md"


def unfenced(text: str) -> list[tuple[int, str]]:
    """``(line number, line)`` outside fenced code; inline code stays, row IDs sit in it."""
    out, fenced = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line):
            fenced = not fenced
        elif not fenced:
            out.append((number, line))
    return out


def section(plan: str, name: str) -> str:
    """Body of the ``## <name>`` section of a plan, or an empty string."""
    lines, body, on = plan.splitlines(), [], False
    for line in lines:
        if line.startswith("## "):
            on = line[3:].strip().lower().startswith(name.lower())
        elif on:
            body.append(line)
    return "\n".join(line for _, line in unfenced("\n".join(body))).strip()


TABLE_ROW_RE = re.compile(r"^\|.*\|$")
TABLE_SEPARATOR_RE = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")
LIST_ITEM_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")


def _seam_items(lines: list[str]) -> list[str]:
    """List items and table data rows; a table header row and its separator row are not seams."""
    items = []
    for index, line in enumerate(lines):
        if TABLE_ROW_RE.match(line):
            is_header = index + 1 < len(lines) and bool(TABLE_SEPARATOR_RE.match(lines[index + 1]))
            if not is_header and not TABLE_SEPARATOR_RE.match(line):
                items.append(line)
        elif LIST_ITEM_RE.match(line):
            items.append(line)
    return items


def seams(plan: str) -> list[str]:
    """One entry per seam of the Cross-repo seams section, none when it says ``none``.

    A seam is a table data row or a list item. The table header row, the separator row and prose
    around a table are not seams. A section with no table and no list keeps one entry per line.
    """
    body = section(plan, "Cross-repo seams")
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines or NO_UNKNOWNS_RE.match(lines[0]):
        return []
    structured = any(TABLE_ROW_RE.match(ln) or LIST_ITEM_RE.match(ln) for ln in lines)
    return _seam_items(lines) if structured else lines


def row_lines(requirements: str) -> list[tuple[str, str]]:
    """``(row ID, row text without inline code)`` of every active row."""
    out = []
    for line in requirements.splitlines():
        match = FIRST_CELL_RE.match(line)
        if match and "RETIRED" not in line:
            out.append((match.group(1), CODE_RE.sub("", line)))
    return out


def check_contracts(spec_dir: Path, plan: str) -> list[str]:
    """One human-written contract document per seam: wire shape, refusal codes, owner rows on both sides."""
    listed = seams(plan)
    if not listed:
        return (
            [] if not (spec_dir / "contracts").exists() else ["plan.md: contracts/ exists but the plan lists no seam"]
        )
    folder = spec_dir / "contracts"
    docs = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in sorted(folder.glob("*.md"))}
    others = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
    out = [f"plan.md: contracts/{n} is not a human-written .md document" for n in others if not n.endswith(".md")]
    if len(docs) < len(listed):
        out.append(f"plan.md: {len(listed)} seam(s) listed and {len(docs)} document(s) in contracts/; one per seam")
    for seam in listed:
        ids = ROW_TOKEN_RE.findall(seam)
        if not any(set(ids) & set(ROW_TOKEN_RE.findall(text)) for text in docs.values()):
            out.append(f"plan.md: seam '{seam[:60]}' has no document in contracts/ citing its row ID")
    for name, text in docs.items():
        low = text.lower()
        out += [f"contracts/{name} lacks the '{s}' section" for s in CONTRACT_SECTIONS if s not in low]
        if not (PROVIDER_RE.search(text) and CONSUMER_RE.search(text)):
            out.append(
                f"contracts/{name} lacks a 'Provider: <repository> <ROW-ID>' or 'Consumer: <repository> <ROW-ID>' line"
            )
    return out


def check_data_model(spec_dir: Path, requirements: str) -> list[str]:
    """A row that adds types, classes or tables needs a ``data-model.md`` with content."""
    adding = [rid for rid, text in row_lines(requirements) if ADDS_RE.search(text)]
    path = spec_dir / "data-model.md"
    if not adding:
        return []
    body = (
        [ln for _, ln in prose(path.read_text(encoding="utf-8")) if ln.strip() and not ln.startswith("#")]
        if path.is_file()
        else []
    )
    return [f"{adding[0]} adds types, classes or tables and data-model.md is missing or empty"] if len(body) < 3 else []


def check_quickstart(spec_dir: Path, requirements: str) -> list[str]:
    """A served behaviour row needs a ``quickstart.md`` naming how to run its proof."""
    served = [rid for rid, text in row_lines(requirements) if SERVED_RE.search(text)]
    path = spec_dir / "quickstart.md"
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    if served and not ("`" in text and RUNNER_RE.search(text)):
        return [
            f"{served[0]} is a served behaviour row and quickstart.md is missing or names no scenario or test command"
        ]
    return []


def check_research(spec_dir: Path, plan: str) -> list[str]:
    """``research.md`` exists exactly when Phase 0 lists unknowns."""
    body = section(plan, "Phase 0")
    unknowns = bool(body) and not NO_UNKNOWNS_RE.match(body) and not body.startswith("[")
    present = (spec_dir / "research.md").is_file()
    if unknowns and not present:
        return ["plan.md: Phase 0 lists unknowns and research.md is missing"]
    return ["plan.md: research.md exists but Phase 0 lists no unknowns"] if present and not unknowns else []


def check_artifacts(spec_dir: Path, texts: Mapping[str, str]) -> list[str]:
    """All optional-artifact findings for one spec directory (file-prefixed messages)."""
    plan, requirements = texts.get("plan.md", ""), texts.get("requirements.md", "")
    found = [*check_contracts(spec_dir, plan), *check_research(spec_dir, plan)]
    found += [*check_data_model(spec_dir, requirements), *check_quickstart(spec_dir, requirements)]
    if not (spec_dir / CHECKLIST).is_file():
        found.append("checklists/requirements.md is missing; fill it from .specify/templates/checklist-template.md")
    return found
