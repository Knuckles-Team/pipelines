"""Release view for the architecture page (PIPE-PAGES-R045).

Reads the release bundle manifests (``releases/*.yml``, PIPE-RELEASE-R021) and reports, per release, its phase,
scenario state, scoped rows per repository and the share VERIFIED. A requirement counts as delivered when it is
VERIFIED (PIPE-PAGES-R044).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

UNSCHEDULED = "unscheduled"
NOT_RUN = "not run"
RUNS_FILE = "scenario-runs.json"
PHASE_RE = re.compile(r"P[1-5]")
MANIFEST_DIR = "releases"
PASSED = "passed"
METRICS = ("provenance_coverage", "conflict_rate", "contradictions", "decay_events")


class ReleaseManifestInvalid(Exception):
    """A release manifest that cannot be read or names a phase outside P1 to P5 (``release-manifest-invalid``)."""

    code = "release-manifest-invalid"


def load_manifests(directory: Path, *, required: bool = False) -> list[dict]:
    """Every ``*.yml`` manifest (JSON syntax) in the directory, ordered by release ID.

    A missing directory is an empty list, or an error when ``required`` (a published build must carry its bundles).
    A manifest that does not parse or names a malformed phase raises ``ReleaseManifestInvalid``.
    """
    if not directory.is_dir():
        if required:
            raise ReleaseManifestInvalid(f"release manifest directory {directory.name}/ is missing")
        return []
    out = []
    for path in sorted(directory.glob("*.yml")):
        try:
            doc = json.loads(path.read_text())
        except ValueError as exc:
            raise ReleaseManifestInvalid(f"{path.name}: not readable: {exc}") from exc
        if not isinstance(doc, dict) or not PHASE_RE.fullmatch(str(doc.get("phase", ""))):
            raise ReleaseManifestInvalid(f"{path.name}: phase must be one of P1 to P5")
        out.append(doc)
    return out


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


def part_progress(manifests: list[dict], rows: list[dict], node_of: dict[str, str]) -> dict[str, list[dict]]:
    """Release ID -> ``[{node, rows, verified}]``: the scoped rows each part owns, ordered by node ID."""
    by_id = {r["id"]: r for r in rows}
    out: dict[str, dict[str, dict]] = {doc["id"]: {} for doc in manifests}
    for rid, rel in row_releases(manifests, rows).items():
        node = node_of.get(rid)
        if node is None:
            continue
        entry = out[rel].setdefault(node, {"node": node, "rows": 0, "verified": 0})
        entry["rows"] += 1
        entry["verified"] += by_id[rid]["status"] == "VERIFIED"
    return {rel: [parts[k] for k in sorted(parts)] for rel, parts in out.items()}


def engine_metrics(runs: dict[str, dict]) -> dict:
    """The four engine metrics of the latest scenario runs, one value per metric or ``None`` when no run reports it."""
    out: dict = {}
    for name in METRICS:
        values = {p: run["metrics"][name] for p, run in sorted(runs.items()) if name in (run.get("metrics") or {})}
        out[name] = values
    return out


def release_view(
    manifests: list[dict],
    rows: list[dict],
    runs: dict[str, dict] | None = None,
    node_of: dict[str, str] | None = None,
) -> dict:
    """The release block embedded in the page: one entry per release, the unscheduled count and the engine metrics."""
    runs = runs or {}
    by_id = {r["id"]: r for r in rows}
    owner = row_releases(manifests, rows)
    progress = part_progress(manifests, rows, node_of or {})
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
                "manifest": f"{MANIFEST_DIR}/{doc['id']}.yml",
                "progress": progress[doc["id"]],
                "repos": [{**e, "specs": sorted(e["specs"])} for _, e in sorted(repos.items())],
            }
        )
    return {
        "releases": releases,
        "unscheduled": sum(1 for rid in by_id if rid not in owner),
        "metrics": engine_metrics(runs),
    }
