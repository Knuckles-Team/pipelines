"""``--write``: apply one proposed mechanical split to a repository's spec
files (section 3 of
``plans/refactor/reconciliation-20261006/SPEC-SIZING-AND-DEPENDENCIES.md``).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

if __package__:
    from .spec_graph_core import Requirement
    from .spec_graph_load import load_repo
    from .spec_graph_parse import TASK_LINE
    from .spec_graph_score import needs_split, propose_split, size_score
else:
    from spec_graph_core import Requirement
    from spec_graph_load import load_repo
    from spec_graph_parse import TASK_LINE
    from spec_graph_score import needs_split, propose_split, size_score


def _insert_after_match(lines: list[str], predicate, new_lines: list[str]) -> list[str]:
    for index, line in enumerate(lines):
        if predicate(line):
            return lines[: index + 1] + new_lines + lines[index + 1 :]
    return lines + new_lines


def _write_requirements_md(path: Path, req: Requirement, children: list[tuple[str, str]]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()

    def is_parent_row(line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith("|") and f"`{req.id}`" in stripped.split("|")[1]

    new_rows = []
    for child_id, scope in children:
        title = f"{req.title} — {scope} slice"
        body = f"**{title}.** Implements the {scope} portion of `{req.id}`."
        verification = f"Verified by the parent requirement's acceptance test, scoped to {scope}."
        new_rows.append(f"| `{child_id}` | {body} | {verification} |")
    lines = _insert_after_match(lines, is_parent_row, new_rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tasks_md(path: Path, req: Requirement, children: list[tuple[str, str]]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    new_lines = [f"- [ ] **{child_id}:** {req.title} — {scope} slice of `{req.id}`." for child_id, scope in children]
    last_task_index = max(
        (i for i, line in enumerate(lines) if TASK_LINE.match(line.strip())),
        default=None,
    )
    if last_task_index is None:
        lines = lines + new_lines
    else:
        lines = lines[: last_task_index + 1] + new_lines + lines[last_task_index + 1 :]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_checker(repo_root: Path):
    checker_path = repo_root / "scripts" / "check_public_specs.py"
    spec = importlib.util.spec_from_file_location("owner_check_public_specs", checker_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def apply_split(repo_root: Path, req_id: str) -> list[str]:
    """Apply one proposed split to ``repo_root``'s spec files; return the new
    child IDs. Raises ``SystemExit`` if the requirement is unknown or does not
    meet the split rule."""
    repo_root = Path(repo_root)
    reqs = load_repo(repo_root)
    req = reqs.get(req_id)
    if req is None:
        raise SystemExit(f"{req_id}: not found under {repo_root}")
    delivery_states = {rid: r.delivery_state for rid, r in reqs.items()}
    score = size_score(req, delivery_states)
    if not needs_split(req, score):
        raise SystemExit(f"{req_id}: size score {score} does not require a split")
    _, children = propose_split(req)
    spec_dir = repo_root / "specs" / req.spec
    _write_requirements_md(spec_dir / "requirements.md", req, children)
    _write_tasks_md(spec_dir / "tasks.md", req, children)
    checker = _load_checker(repo_root)
    errors = checker.problems(repo_root)
    if errors:
        raise SystemExit(f"{req_id}: split applied but check_public_specs failed:\n" + "\n".join(errors))
    return [cid for cid, _ in children]
