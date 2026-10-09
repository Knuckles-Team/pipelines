"""spec-decomposition: every ``specs/<dir>/`` with a status.json decomposes IDs consistently.

Detection only -- it never rewrites a spec. The repair tool lives in a different
repository (``plans/tools/l9/spec_decomp_fix.py``) and is a read-only reference for
this gate's logic, not something this gate calls.

For each ``specs/<dir>/`` that has a ``status.json``, across that directory's own
``requirements.md``, ``tasks.md``, ``test-spec.md`` and ``status.json``:

(a) an ID appears twice, in requirements.md table rows or in status.json rows;
(b) a child ID ``<ID>.<n>`` referenced in requirements.md, tasks.md or test-spec.md
    has no status.json row;
(c) a status.json row has no requirements.md row;
(d) a parent is LANDED/ACCEPTED while any of its (tracked) children is not;
(e) a child exists (tracked in status.json, or merely referenced) but its parent
    has no row at all, neither in status.json nor in requirements.md.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root

#: An ID family token, e.g. ``PIPE-IDENTITY-R001`` or a child ``PIPE-IDENTITY-R001.2``.
ID = r"[A-Z][A-Z0-9-]*-R?\d{2,3}(?:\.\d+)*"
ID_RE = re.compile(ID)
ROW_RE = re.compile(r"^\|\s*`?(" + ID + r")`?\s*\|")
#: Delivery states that satisfy "the parent is LANDED/ACCEPTED" in (d).
PARENT_DONE = {"LANDED", "ACCEPTED"}
#: Delivery states that satisfy "the child is done" when checking (d).
CHILD_DONE = {"LANDED", "ACCEPTED", "CLOSED", "RETIRED"}


def parent_of(id_: str) -> str | None:
    """The immediate parent of a dotted child ID, or ``None`` for a root ID."""
    m = re.match(r"(.+)\.\d+$", id_)
    return m.group(1) if m else None


def _row_ids(text: str) -> Counter[str]:
    """Every requirements.md table-row ID, counted (a row leads its line with ``| ID |``)."""
    counts: Counter[str] = Counter()
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if m:
            counts[m.group(1)] += 1
    return counts


def _status_rows(status: object) -> list[dict]:
    """The requirement rows of a parsed status.json, in whatever shape it was written."""
    reqs = status["requirements"] if isinstance(status, dict) and "requirements" in status else status
    if not isinstance(reqs, list):
        return []
    return [r for r in reqs if isinstance(r, dict) and r.get("id")]


def _referenced_child_ids(texts: dict[str, str]) -> set[str]:
    """Every dotted child ID mentioned anywhere across the spec's own markdown files."""
    found: set[str] = set()
    for text in texts.values():
        for match in ID_RE.findall(text):
            if parent_of(match):
                found.add(match)
    return found


def check_spec(spec_dir: Path) -> list[str]:
    """Findings for one ``specs/<dir>/``; an empty list means clean."""
    status_path = spec_dir / "status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CannotRun(f"{status_path}: invalid status.json ({exc})") from exc

    texts = {
        name: (spec_dir / name).read_text(encoding="utf-8")
        for name in ("requirements.md", "tasks.md", "test-spec.md")
        if (spec_dir / name).is_file()
    }
    req_counts = _row_ids(texts.get("requirements.md", ""))

    rows = _status_rows(status)
    status_counts: Counter[str] = Counter(r["id"] for r in rows)
    # First row wins for state lookups; duplicates themselves are flagged by (a).
    state_by_id: dict[str, str] = {}
    for r in rows:
        state_by_id.setdefault(r["id"], r.get("delivery_state") or "")

    label = spec_dir.name
    findings: list[str] = []

    # (a) an ID appears twice, in requirements.md rows or in status.json rows.
    for id_, count in sorted(req_counts.items()):
        if count > 1:
            findings.append(f"{label}: duplicate ID {id_} appears {count}x in requirements.md")
    for id_, count in sorted(status_counts.items()):
        if count > 1:
            findings.append(f"{label}: duplicate ID {id_} appears {count}x in status.json")

    # (b) a referenced child has no status.json row.
    referenced = _referenced_child_ids(texts)
    for id_ in sorted(referenced):
        if id_ not in status_counts:
            findings.append(f"{label}: child {id_} is referenced but has no status.json row")

    # (c) a status.json row has no requirements.md row.
    for id_ in sorted(status_counts):
        if id_ not in req_counts:
            findings.append(f"{label}: status.json row {id_} has no requirements.md row")

    # (d) a parent is LANDED/ACCEPTED while any of its tracked children is not.
    children_of: dict[str, list[str]] = {}
    for id_ in status_counts:
        parent = parent_of(id_)
        if parent:
            children_of.setdefault(parent, []).append(id_)
    for parent, children in sorted(children_of.items()):
        if state_by_id.get(parent) in PARENT_DONE:
            for child in sorted(children):
                child_state = state_by_id.get(child) or ""
                if child_state not in CHILD_DONE:
                    findings.append(
                        f"{label}: parent {parent} is {state_by_id.get(parent)} but "
                        f"child {child} is {child_state or 'UNKNOWN'}"
                    )

    # (e) a child exists (tracked or merely referenced) but its parent has no row at all.
    for id_ in sorted({*status_counts, *referenced}):
        parent = parent_of(id_)
        if parent and parent not in status_counts and parent not in req_counts:
            findings.append(f"{label}: child {id_} exists but parent {parent} has no row at all")

    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spec-decomposition", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    findings: list[str] = []
    checked = 0
    for status_path in sorted(root.glob("specs/*/status.json")):
        checked += 1
        findings.extend(check_spec(status_path.parent))
    if not findings:
        print(f"spec decomposition: clean ({checked} spec(s) checked)")
        return 0
    print("FAIL: spec decomposition is inconsistent.")
    for finding in findings:
        print(f"  {finding}")
    return 1
