"""Agent export of the Canopy rows (PIPE-PAGES-R057).

One JSON file and one Markdown file list every spec row with the exact repository-relative path of each artifact it
lives in, so an agent can act on a row without scraping the page. The files are build outputs, never committed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
EXPORT_DIR = "export"
MODES = ("architecture", "delivery", "sdd", "priority", "dependency")
FILTERS = ("research", "plan", "ready", "verify")
ARTIFACTS = ("requirements", "spec", "plan", "tasks", "test-spec", "research")
ARTIFACT_FILES = {
    "requirements": "requirements.md",
    "spec": "spec.md",
    "plan": "plan.md",
    "tasks": "tasks.md",
    "test-spec": "test-spec.md",
    "research": "research.md",
}
OWNER_URL = "https://github.com/Knuckles-Team"


class ExportRefused(Exception):
    """The export cannot be written: ``unsafe-path`` or ``export-row-missing``."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class ExportRow:
    """One spec row with the paths of its artifacts."""

    id: str
    title: str
    repo: str
    family: str
    part: str
    state: str
    phase: str
    priority: int | float | None
    release: str
    line: int
    files: dict = field(default_factory=dict)
    next_step: str = ""
    open_questions: int = 0


@dataclass(frozen=True)
class ViewSpec:
    """The view in force: mode, Next-step filters, release and the row the drawer shows."""

    mode: str = "architecture"
    filters: tuple[str, ...] = ()
    release: str = ""
    row: str = ""

    def validate(self) -> None:
        if self.mode not in MODES:
            raise ExportRefused("unknown-mode", self.mode)
        for name in self.filters:
            if name not in FILTERS:
                raise ExportRefused("unknown-filter", name)


def _safe(path: str) -> bool:
    return bool(path) and not path.startswith("/") and ".." not in path.split("/") and "\\" not in path


def _rel_paths(snap, family: str) -> dict:
    """Repository-relative path of each artifact present in the family, plus the checklist list."""
    base = f"specs/{family}/"
    files = {k: base + name for k, name in ARTIFACT_FILES.items() if base + name in snap.files}
    files["checklists"] = sorted(f for f in snap.files if f.startswith(base + "checklists/"))
    return files


def build_rows(snaps: list, rows: list[dict], delivery: dict) -> list[ExportRow]:
    """Return one ExportRow per scanned row, sorted by repository and ID. Raises ``ExportRefused`` on an unsafe path."""
    by_repo = {s.repo: s for s in snaps}
    cards = delivery.get("cards", {})
    parts = delivery.get("row_node", {})
    questions = delivery.get("row_questions", {})
    out = []
    for row in rows:
        snap = by_repo[row["repo"]]
        files = _rel_paths(snap, row["family"])
        for path in [v for v in files.values() if isinstance(v, str)] + files["checklists"]:
            if not _safe(path):
                raise ExportRefused("unsafe-path", path)
        card = cards.get(row["repo"], {}).get(row["family"], {})
        out.append(
            ExportRow(
                id=row["id"],
                title=row.get("title", ""),
                repo=row["repo"],
                family=row["family"],
                part=parts.get(row["id"], ""),
                state=row["status"],
                phase=card.get("p", ""),
                priority=delivery.get("scores", {}).get(row["id"], {}).get("priority"),
                release=delivery.get("release_of", {}).get(row["id"], "unscheduled"),
                line=row.get("line", 0),
                files=files,
                next_step=delivery.get("row_next", {}).get(row["id"], ""),
                open_questions=questions.get(row["id"], 0),
            )
        )
    out.sort(key=lambda r: (r.repo, r.id))
    missing = sorted(f"{s.repo}:{r['id']}" for s in snaps for r in s.rows)
    exported = {f"{r.repo}:{r.id}" for r in out}
    lost = [m for m in missing if m not in exported]
    if lost:
        raise ExportRefused("export-row-missing", ", ".join(lost[:5]))
    return out


def digest(rows: list[ExportRow]) -> str:
    """sha256 over the canonical JSON of the row list."""
    blob = json.dumps([asdict(r) for r in rows], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def header(rows: list[ExportRow], heads: dict[str, str], view: ViewSpec, built_at: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "built_at": built_at,
        "heads": dict(sorted(heads.items())),
        "row_count": len(rows),
        "view": {"mode": view.mode, "filters": list(view.filters), "release": view.release, "row": view.row},
        "digest": digest(rows),
    }


def markdown_line(row: ExportRow, slug: str) -> str:
    paths = [v for v in row.files.values() if isinstance(v, str)] + list(row.files.get("checklists", []))
    return f"- [{row.id}]({OWNER_URL}/{slug}/blob/HEAD/specs/{row.family}/requirements.md) {row.state} - {', '.join(paths)}"


def write_export(
    page_dir: Path, snaps: list, rows: list[dict], delivery: dict, view: ViewSpec | None = None, built_at: str = ""
) -> list[Path]:
    """Write ``export/rows.json`` and ``export/rows.md`` beside the page and return both paths.

    Two builds of equal input give equal bytes except the ``built_at`` header field.
    """
    view = view or ViewSpec()
    view.validate()
    built_at = built_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    export_rows = build_rows(snaps, rows, delivery)
    head = header(export_rows, {s.repo: s.head for s in snaps if s.head}, view, built_at)
    slugs = {s.repo: s.slug for s in snaps}
    root = page_dir / EXPORT_DIR
    root.mkdir(parents=True, exist_ok=True)
    json_path, md_path = root / "rows.json", root / "rows.md"
    json_path.write_text(
        json.dumps({**head, "rows": [asdict(r) for r in export_rows]}, indent=1, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    top = ["# Canopy rows", "", "```json", json.dumps(head, indent=1, sort_keys=True), "```", ""]
    md_path.write_text(
        "\n".join(top + [markdown_line(r, slugs.get(r.repo, r.repo)) for r in export_rows]) + "\n", encoding="utf-8"
    )
    return [json_path, md_path]
