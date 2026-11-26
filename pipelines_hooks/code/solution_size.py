"""Total solution-size measurement for candidate comparison.

``SolutionSizeEvidence`` records first-party source bytes, nonblank lines and syntax-node counts
per language adapter over a declared scope, unchanged files included.  A changed-line count is a
separate field and never stands for size.  Generated and vendor content is excluded only by an
explicit category with a producer.  Comparison needs an adequacy receipt per candidate and an
identical scope: a candidate whose behavior receipt fails is ineligible however small, and a
missing receipt, mismatched scope or unsupported syntax adapter is ``CannotRun`` so the comparison
stays unavailable.  This module measures only; choosing among adequate candidates is the engine's.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

ADAPTERS = {".py": "python-ast/v1"}


@dataclass(frozen=True)
class SolutionSizeEvidence:
    snapshot_digest: str
    scope: tuple[str, ...]
    adapter_versions: dict[str, str]
    total_bytes: int
    nonblank_lines: int
    syntax_nodes: dict[str, int]
    exclusions: tuple[dict[str, str], ...]
    changed_lines: int | None = None
    files: tuple[str, ...] = field(default=())


def measure(
    root: Path, scope: tuple[str, ...], exclusions: tuple[dict[str, str], ...] = (), *, changed_lines: int | None = None
) -> SolutionSizeEvidence:
    for item in exclusions:
        if not item.get("category") or not item.get("producer") or not item.get("path"):
            raise CannotRun(f"exclusion {item!r} needs a path, a category and a producer")
    excluded = {item["path"] for item in exclusions}
    digest = hashlib.sha256()
    total = lines = 0
    nodes: dict[str, int] = {}
    files: list[str] = []
    for entry in scope:
        for path in sorted((root / entry).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            if rel in excluded:
                continue
            adapter = ADAPTERS.get(path.suffix)
            if adapter is None:
                raise CannotRun(
                    f"{rel}: no syntax adapter for {path.suffix or 'this file'}; size comparison unavailable"
                )
            data = path.read_bytes()
            try:
                tree = ast.parse(data.decode("utf-8"), filename=rel)
            except (SyntaxError, UnicodeError) as exc:
                raise CannotRun(f"{rel}: cannot be parsed by {adapter}: {exc}") from exc
            digest.update(rel.encode() + b"\0" + data)
            total += len(data)
            lines += sum(1 for line in data.decode("utf-8").splitlines() if line.strip())
            nodes[adapter] = nodes.get(adapter, 0) + sum(1 for _ in ast.walk(tree))
            files.append(rel)
    if not files:
        raise CannotRun(f"no first-party source under {list(scope)}")
    return SolutionSizeEvidence(
        digest.hexdigest(), scope, dict(ADAPTERS), total, lines, nodes, exclusions, changed_lines, tuple(files)
    )


def compare(
    baseline: SolutionSizeEvidence,
    candidate: SolutionSizeEvidence,
    receipts: dict[str, object],
    decision: str | None = None,
) -> dict[str, object]:
    """Absolute and delta size; eligible only with passing adequacy receipts for both snapshots."""
    if baseline.scope != candidate.scope:
        raise CannotRun("baseline and candidate were measured over different scopes")
    ids = receipts.get("receipts")
    if not isinstance(ids, list) or not ids:
        raise CannotRun("no adequacy receipts: minimalism comparison is unavailable")
    bound = {r.get("snapshot"): r for r in ids if isinstance(r, dict)}
    for evidence in (baseline, candidate):
        if evidence.snapshot_digest not in bound:
            raise CannotRun(f"no adequacy receipt for snapshot {evidence.snapshot_digest[:12]}")
    eligible = all(bound[e.snapshot_digest].get("behavior") == "pass" for e in (baseline, candidate))
    return {
        "eligible": eligible,
        "baseline": asdict(baseline),
        "candidate": asdict(candidate),
        "delta": {
            "total_bytes": candidate.total_bytes - baseline.total_bytes,
            "nonblank_lines": candidate.nonblank_lines - baseline.nonblank_lines,
            "syntax_nodes": {
                k: candidate.syntax_nodes.get(k, 0) - baseline.syntax_nodes.get(k, 0) for k in baseline.syntax_nodes
            },
        },
        "adequacy_receipts": sorted(str(r.get("id")) for r in bound.values()),
        "owner_decision": decision,
        "shortcut_comment_policy": "unresolved: reserved for the coordinator; not measured here",
    }


def load_receipts(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRun(f"adequacy receipts unreadable: {exc!r}") from exc
    if not isinstance(data, dict):
        raise CannotRun("adequacy receipts must be an object")
    return data
