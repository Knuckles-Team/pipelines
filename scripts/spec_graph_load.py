"""Load every tracked, non-template spec under one or more repository roots
into ``Requirement`` objects, resolving cross-repo dependency mentions.
"""

from __future__ import annotations

import json
from pathlib import Path

if __package__:
    from .spec_graph_core import Requirement
    from .spec_graph_parse import FILE_HANDLERS, parse_requirements_md
else:
    from spec_graph_core import Requirement
    from spec_graph_parse import FILE_HANDLERS, parse_requirements_md


def _status_data(status_path: Path) -> dict | None:
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _requirement_from_entry(
    rid: str,
    *,
    repo_name: str,
    spec_name: str,
    meta: dict,
    rows: dict[str, tuple[str, str]],
    fallback_state: str,
) -> Requirement:
    requirement_text, verification_text = rows.get(rid, ("", ""))
    return Requirement(
        id=rid,
        repo=repo_name,
        spec=spec_name,
        title=meta.get("title") or rid,
        delivery_state=meta.get("delivery_state", fallback_state),
        requirement_text=requirement_text,
        verification_text=verification_text,
    )


def _requirements_from_status(
    data: dict, *, repo_name: str, spec_dir: Path, reqs: dict[str, Requirement]
) -> None:
    entries = {
        entry["id"]: entry
        for entry in data.get("requirements", []) or []
        if isinstance(entry, dict) and entry.get("id")
    }
    req_md = spec_dir / "requirements.md"
    rows = (
        parse_requirements_md(req_md.read_text(encoding="utf-8"))
        if req_md.is_file()
        else {}
    )
    fallback_state = data.get("delivery_state", "UNKNOWN")
    for rid in data.get("requirement_ids", []) or []:
        if isinstance(rid, str) and rid:
            reqs[rid] = _requirement_from_entry(
                rid,
                repo_name=repo_name,
                spec_name=spec_dir.name,
                meta=entries.get(rid, {}),
                rows=rows,
                fallback_state=fallback_state,
            )


def _load_status_entries(root: Path, reqs: dict[str, Requirement]) -> list[Path]:
    """Populate ``reqs`` from every spec's ``status.json`` under ``root`` and
    return the spec directories found, without yet walking their other files.

    Loading every root's declared requirement IDs before any file is scanned
    for dependency mentions is what lets ``add_edge`` tell a real,
    cross-repo-or-not requirement ID apart from a spec file's own local
    test/case numbering scheme that merely has the same textual shape."""
    root = Path(root)
    specs_dir = root / "specs"
    if not specs_dir.is_dir():
        return []
    spec_dirs = sorted(
        p for p in specs_dir.iterdir() if p.is_dir() and p.name != "_template"
    )
    for spec_dir in spec_dirs:
        status_path = spec_dir / "status.json"
        if not status_path.is_file():
            continue
        data = _status_data(status_path)
        if data is not None:
            _requirements_from_status(
                data, repo_name=root.name, spec_dir=spec_dir, reqs=reqs
            )
    return spec_dirs


def _apply_spec_dir_files(spec_dir: Path, reqs: dict[str, Requirement]) -> None:
    for filename, handler in FILE_HANDLERS.items():
        path = spec_dir / filename
        if path.is_file():
            handler(path.read_text(encoding="utf-8"), reqs)


def load_repos(roots: list[Path]) -> dict[str, Requirement]:
    """Load every given repository root's Requirements as one combined graph,
    so a cross-repo dependency mention resolves correctly regardless of root
    order (see ``_load_status_entries``)."""
    reqs: dict[str, Requirement] = {}
    spec_dirs: list[Path] = []
    for root in roots:
        spec_dirs.extend(_load_status_entries(root, reqs))
    for spec_dir in spec_dirs:
        _apply_spec_dir_files(spec_dir, reqs)
    return reqs


def load_repo(root: Path) -> dict[str, Requirement]:
    """Load a single repository root's Requirements (see ``load_repos``)."""
    return load_repos([root])
