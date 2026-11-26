"""spec-glossary: a repository's specs use its glossary and the ontology mapping (PIPE-GATES-R100).

The glossary ``specs/glossary.md`` is a table ``| Term | Class | Synonyms |``: one term, the
spec-driven-development ontology class it maps to, and the comma-separated synonyms the specs
must not use. The gate reports a term with no class, an unknown class, a duplicate term, and a
synonym used in a row of a spec the change adds or edits (an untouched spec is advisory). It also
reports a leaf row that lacks the typed fields the ontology ingests: a ``Depends:`` clause, a
``Test:`` or ``Tests:`` field, and, when the row has a ``Refusal:`` clause, an exit status or a
backticked code in it. A row the change does not add or edit is advisory.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.specs import narrative
from pipelines_hooks.specs.ids import ROW_RE
from pipelines_hooks.specs.requirements_doc import parse_rows

ADVISORY = " [advisory]"
#: The classes of the spec-driven-development ontology a term may map to.
CLASSES = (
    "Requirement",
    "RequirementRow",
    "Specification",
    "SpecFolder",
    "ImplementationPlan",
    "PlanSection",
    "SpecTask",
    "TaskLine",
    "TestCase",
    "Contract",
    "AcceptanceCriteria",
    "ChecklistItem",
    "ConstitutionPrinciple",
    "DeliveryGoal",
    "DeliveryPhase",
    "ReleaseBundle",
    "SoftwareFeature",
    "DesignGuideline",
    "ComplianceConstraint",
)
_CODE = re.compile(r"`[^`\n]*`")
_FIELD = {
    "Depends": re.compile(r"\bDepends(?: on)?:"),
    "Test": re.compile(r"\bTests?:|\|\s*Tests?\b"),
}


def read_glossary(path: Path) -> tuple[list[tuple[int, str, str, tuple[str, ...]]], list[str]]:
    """``(line, term, class, synonyms)`` entries and the findings of the glossary itself."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"cannot read the glossary {path}: {exc}") from exc
    name, entries, found, seen = path.name, [], [], {}
    for number, line in enumerate(text.splitlines(), 1):
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        if not cells or cells[0].lower() == "term" or set("".join(cells)) <= set("-: "):
            continue
        term, cls = cells[0].strip("`*"), (cells[1].strip("`*") if len(cells) > 1 else "")
        synonyms = tuple(s.strip("`* ") for s in (cells[2].split(",") if len(cells) > 2 else []) if s.strip("`* "))
        if not cls:
            found.append(f"{name}:{number}: term '{term}' has no class; expected one of {', '.join(CLASSES)}")
        elif cls not in CLASSES:
            found.append(
                f"{name}:{number}: term '{term}' maps to unknown class '{cls}'; expected one of {', '.join(CLASSES)}"
            )
        if term.casefold() in seen:
            found.append(f"{name}:{number}: duplicate term '{term}' (first at line {seen[term.casefold()]})")
        seen.setdefault(term.casefold(), number)
        entries.append((number, term, cls, synonyms))
    return entries, found


def synonym_findings(spec: str, text: str, entries, base: int = 0) -> list[str]:
    """A defined-term synonym used in a row line, outside code spans."""
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        if not ROW_RE.match(line):
            continue
        prose = _CODE.sub(" ", line)
        for _, term, _, synonyms in entries:
            for word in synonyms:
                if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", prose, re.I):
                    row = ROW_RE.match(line).group(1)
                    out.append(f"{spec}:{number}: row {row} uses '{word}', a synonym of the defined term '{term}'")
    return out


def field_findings(spec: str, text: str) -> list[tuple[str, str]]:
    """``(row ID, finding)`` for each leaf row that lacks a typed field the ontology needs."""
    rows = parse_rows(text)
    ids = {r.id for r in rows}
    leaves = {i for i in ids if not any(o.startswith(i + ".") for o in ids)}
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        match = ROW_RE.match(line)
        if not match or match.group(1) not in leaves or "RETIRED" in line:
            continue
        row = match.group(1)
        where = f"{spec}:{number}: row {row}"
        for field, pattern in _FIELD.items():
            if not pattern.search(line):
                out.append((row, f"{where} lacks a typed '{field}:' field"))
        refusal = re.search(r"\bRefusal:(?P<body>[^|]*)", line)
        if refusal and not re.search(r"\bexit\b|`[^`\n]+`", refusal.group("body"), re.I):
            out.append((row, f"{where} has a Refusal: clause with no exit status or code"))
    return out


def findings(root: Path, glossary: Path, base: str | None = None) -> list[str]:
    """Every finding; one outside the change (an untouched spec or row) carries ``ADVISORY``."""
    entries, found = read_glossary(glossary)
    touched = narrative.touched_paths(root, base)
    for spec_dir in sorted(d for d in (root / "specs").glob("*/") if (d / "requirements.md").is_file()):
        rel = f"specs/{spec_dir.name}/requirements.md"
        text = (spec_dir / "requirements.md").read_text(encoding="utf-8", errors="replace")
        tag = "" if narrative.is_touched(touched, spec_dir, root, "requirements.md") else ADVISORY
        found += [m + tag for m in synonym_findings(rel, text, entries)]
        added = narrative.added_row_ids(root, spec_dir, touched, base)
        found += [m + ("" if row in added else ADVISORY) for row, m in field_findings(rel, text)]
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spec-glossary", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--glossary", type=Path, default=Path("specs/glossary.md"))
    parser.add_argument("--base", default=None, help="revision the change is measured against")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    glossary = args.glossary if args.glossary.is_absolute() else root / args.glossary
    found = findings(root, glossary, args.base)
    failing = [f for f in found if not f.endswith(ADVISORY)]
    for finding in found:
        print(f"spec-glossary: {finding}" if finding in failing else f"ADV spec-glossary: {finding}")
    if failing:
        print(f"spec-glossary: FAIL: {len(failing)} finding(s)")
        return 1
    print("spec-glossary: clean")
    return 0
