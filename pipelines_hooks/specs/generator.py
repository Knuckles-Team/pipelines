"""Generate every ``specs/*/status.json`` (SPEC-STATUS-LIFECYCLE.md Sec1-4).

A pure function of git history, requirements.md and the test tree: no build,
no network. ``status.json`` is machine output (schema_version 2); a
hand-edited copy is simply overwritten by the next ``--write``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.specs.bindings import test_bindings
from pipelines_hooks.specs.git_log import landing_commits, reachable_shas
from pipelines_hooks.specs.legacy import legacy_landings
from pipelines_hooks.specs.records import build_record, mentioned_tokens
from pipelines_hooks.specs.requirements_doc import Row, parse_rows
from pipelines_hooks.specs.rollup import apply_rollup, overall_state

SCHEMA_VERSION = 2


class Evidence(NamedTuple):
    """Everything a requirement row's delivery state is computed from."""

    landed_by: dict[str, set[str]]
    tested_by: dict[str, list[str]]
    legacy_by: dict[str, list[str]]


def _load_status(path: Path) -> dict:
    """The previously published document, or ``{}`` for a new one."""
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CannotRun(f"{path}: not valid JSON ({exc})") from exc
    return loaded if isinstance(loaded, dict) else {}


def _requirement_state(rid: str, evidence: Evidence) -> tuple[list[str], list[str]]:
    landed = sorted(evidence.landed_by.get(rid, set()) | set(evidence.legacy_by.get(rid, [])))
    tests = sorted(set(evidence.tested_by.get(rid, [])))
    return landed, tests


def _spec_document(spec_dir: Path, *, old: dict, rows: list[Row], evidence: Evidence, owner: str) -> dict:
    ids = [row.id for row in rows]
    state: dict[str, str] = {}
    records: dict[str, dict[str, object]] = {}
    for row in rows:
        landed, tests = _requirement_state(row.id, evidence)
        records[row.id] = build_record(row, landed, tests)
        state[row.id] = records[row.id]["delivery_state"]
    apply_rollup(ids, state, records)
    return {
        "schema_version": SCHEMA_VERSION,
        "spec_id": old.get("spec_id") or spec_dir.name,
        "owner_repo": old.get("owner_repo") or owner,
        "delivery_state": overall_state(state),
        "requirement_ids": ids,
        "requirements": [records[rid] for rid in ids],
    }


def generate(repo: Path, head: str) -> dict[Path, dict]:
    """status.json path -> generated document, for every ``specs/*/requirements.md``."""
    commits = landing_commits(repo, head)
    landed_by = mentioned_tokens(commits)
    tested_by = test_bindings(repo)
    on_head = reachable_shas(repo, head)
    owner = repo.resolve().name
    result: dict[Path, dict] = {}
    for requirements_path in sorted(repo.glob("specs/*/requirements.md")):
        spec_dir = requirements_path.parent
        status_path = spec_dir / "status.json"
        old = _load_status(status_path)
        evidence = Evidence(landed_by, tested_by, legacy_landings(old, lambda sha: sha in on_head))
        rows = parse_rows(requirements_path.read_text(encoding="utf-8"))
        result[status_path] = _spec_document(spec_dir, old=old, rows=rows, evidence=evidence, owner=owner)
    return result
