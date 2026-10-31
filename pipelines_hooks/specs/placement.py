"""spec-standard: artifact names and placement under ``specs/`` and ``.specify/``.

Constitution article XXII. Every name is lower-case kebab-case, except a file a tool requires in
upper case. A spec directory is the stable lower-case family ID with no numeric prefix. Plans live
only in ``specs/<family>/plan.md``, templates only in ``.specify/templates/`` and the constitution
only in ``.specify/memory/``. Recorded ``evidence/`` files keep the name of the tool that wrote them.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Files a tool requires in upper case.
UPPER_CASE_ALLOWED = frozenset({"README.md", "AGENTS.md", "CLAUDE.md", "SKILL.md", "LICENSE", "CHANGELOG.md"})
NAME_RE = re.compile(r"^\.?[a-z0-9]+(?:[-.][a-z0-9]+)*$")
NUMERIC_PREFIX_RE = re.compile(r"^\d+-")
ROOTS = ("specs", ".specify")
EVIDENCE = "evidence"


def _walk(root: Path) -> list[Path]:
    """Repository-relative paths of every file and directory under the roots, outside ``evidence/``."""
    found: list[Path] = []
    for name in ROOTS:
        base = root / name
        if base.is_dir():
            found += [p.relative_to(root) for p in sorted(base.rglob("*")) if EVIDENCE not in p.relative_to(base).parts]
    return found


def _name_findings(rel: Path) -> list[str]:
    own = rel.name
    if own in UPPER_CASE_ALLOWED or NAME_RE.match(own):
        return []
    return [
        f"{rel.as_posix()}: names are lower-case kebab-case (allowed upper case: {', '.join(sorted(UPPER_CASE_ALLOWED))})"
    ]


def _placement_findings(rel: Path) -> list[str]:
    parts, own = rel.parts, rel.name.lower()
    in_templates = parts[:2] == (".specify", "templates")
    in_memory = parts[:2] == (".specify", "memory")
    out = []
    if parts[:2] == ("specs", "_template"):
        out.append(f"{rel.as_posix()}: templates live only in .specify/templates/")
    if parts[0] == "specs" and len(parts) > 1 and NUMERIC_PREFIX_RE.match(parts[1]):
        out.append(f"{rel.as_posix()}: a spec directory is the stable family ID with no numeric prefix")
    if "constitution" in own and not in_memory and not (in_templates and own == "constitution-template.md"):
        out.append(f"{rel.as_posix()}: the constitution lives only in .specify/memory/")
    if own.endswith("-template.md") and not in_templates:
        out.append(f"{rel.as_posix()}: templates live only in .specify/templates/")
    is_plan = re.fullmatch(r"(?:.*-)?plans?(?:\.md)?", own) is not None
    if is_plan and not in_templates and rel.parts != ("specs", parts[1] if len(parts) > 1 else "", "plan.md"):
        out.append(f"{rel.as_posix()}: plans live only in specs/<family>/plan.md")
    return out


def check_placement(root: Path) -> list[tuple[str, str]]:
    """``(path, finding)`` for every misnamed or misplaced artifact under ``specs/`` and ``.specify/``."""
    out = []
    for rel in _walk(root):
        out += [(rel.as_posix(), f) for f in (*_name_findings(rel), *_placement_findings(rel))]
    return out
