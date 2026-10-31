"""Release view for the architecture page (PIPE-PAGES-R045).

Reads the release bundle manifests (``releases/*.yml``, PIPE-RELEASE-R021) and reports, per release, its phase,
scenario state, scoped rows per repository and the share VERIFIED. A requirement counts as delivered when it is
VERIFIED (PIPE-PAGES-R044).
"""

from __future__ import annotations

import json
from pathlib import Path

UNSCHEDULED = "unscheduled"
NOT_RUN = "not run"
RUNS_FILE = "scenario-runs.json"


def load_manifests(directory: Path) -> list[dict]:
    """Every ``*.yml`` manifest (JSON syntax) in the directory, ordered by release ID."""
    if not directory.is_dir():
        return []
    return [json.loads(p.read_text()) for p in sorted(directory.glob("*.yml"))]


def load_runs(directory: Path) -> dict[str, dict]:
    """Latest ScenarioRun result per phase, when a record is published beside the manifests."""
    path = directory / RUNS_FILE
    return json.loads(path.read_text()) if path.is_file() else {}


def row_releases(manifests: list[dict], rows: list[dict]) -> dict[str, str]:
    """Row ID -> release ID. A named row keeps its first (earliest) release; an ``all-remaining`` release takes the rest."""
    known = {r["id"] for r in rows}
    out: dict[str, str] = {}
    remaining = ""
    for doc in manifests:
        if doc.get("scope") == "all-remaining":
            remaining = doc["id"]
            continue
        for entry in doc["scope"]:
            for rid in entry["roots"]:
                if rid in known:
                    out.setdefault(rid, doc["id"])
    if remaining:
        for rid in known - out.keys():
            out[rid] = remaining
    return out


def release_view(manifests: list[dict], rows: list[dict], runs: dict[str, dict] | None = None) -> dict:
    """The release block embedded in the page: one entry per release, plus the count of unscheduled rows."""
    runs = runs or {}
    by_id = {r["id"]: r for r in rows}
    owner = row_releases(manifests, rows)
    releases = []
    for doc in manifests:
        scoped = [by_id[rid] for rid, rel in owner.items() if rel == doc["id"]]
        repos: dict[str, dict] = {}
        for r in scoped:
            entry = repos.setdefault(r["repo"], {"repo": r["repo"], "rows": 0, "verified": 0, "specs": set()})
            entry["rows"] += 1
            entry["verified"] += r["status"] == "VERIFIED"
            entry["specs"].add(r.get("spec_id") or r["family"])
        verified = sum(r["status"] == "VERIFIED" for r in scoped)
        run = runs.get(doc["phase"], {})
        releases.append(
            {
                "id": doc["id"],
                "name": doc["name"],
                "phase": doc["phase"],
                "scenario": doc["scenario"],
                "scenario_state": run.get("state", NOT_RUN),
                "rows": len(scoped),
                "verified": verified,
                "share": round(100 * verified / len(scoped)) if scoped else 0,
                "repos": [{**e, "specs": sorted(e["specs"])} for _, e in sorted(repos.items())],
            }
        )
    return {"releases": releases, "unscheduled": sum(1 for rid in by_id if rid not in owner)}
