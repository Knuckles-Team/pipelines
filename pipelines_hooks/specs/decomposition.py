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

Each failure kind (a)-(e) is checked by its own ``find_*`` function in
``decomposition_checks.py``; this module only builds the per-spec index and
runs those checks.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.specs.decomposition_checks import (
    SpecIndex,
    find_duplicates,
    find_orphan_children,
    find_parent_done_child_open,
    find_status_without_requirement,
    find_untracked_children,
    parent_of,
)

#: An ID family token, e.g. ``PIPE-IDENTITY-R001`` or a child ``PIPE-IDENTITY-R001.2``.
ID = r"[A-Z][A-Z0-9-]*-R?\d{2,3}(?:\.\d+)*"
ID_RE = re.compile(ID)
ROW_RE = re.compile(r"^\|\s*`?(" + ID + r")`?\s*\|")


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

    idx = SpecIndex(
        label=spec_dir.name,
        req_counts=req_counts,
        status_counts=status_counts,
        state_by_id=state_by_id,
        referenced=_referenced_child_ids(texts),
    )

    return [
        *find_duplicates(idx),
        *find_untracked_children(idx),
        *find_status_without_requirement(idx),
        *find_parent_done_child_open(idx),
        *find_orphan_children(idx),
    ]


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
