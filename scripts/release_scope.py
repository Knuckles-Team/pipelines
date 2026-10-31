"""Derive release bundle manifests from the phase scenarios (PIPE-RELEASE-R021).

Each phase scenario row (``ARBORA-ACCEPTANCE-R006.1`` to ``.4``) names the requirement rows it exercises. A phase's
scope is those rows plus the transitive closure of their ``Depends on`` rows across every registered repository. A
row belongs to the earliest phase that reaches it. Phase P5 takes every remaining row.

Manifests are written to ``releases/<id>.yml`` as JSON, which is valid YAML, so no YAML library is needed.

Usage:
  python scripts/release_scope.py --workspace /path/to/workspace            # write releases/
  python scripts/release_scope.py --workspace /path/to/workspace --check    # fail on a duplicate or missing row
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.architecture_explorer.sources import requirement_text, snapshot  # noqa: E402

RELEASES = ROOT / "releases"
REGISTRY = ROOT / "scripts/architecture_explorer/registry.json"
SCENARIO_REPO = "agent-packages/arbora"
SCENARIO_FILE = "specs/acceptance-evidence-freeze/requirements.md"
SCENARIOS = {
    "P1": ("ARBORA-ACCEPTANCE-R006.1", "Minimal closed loop on one node"),
    "P2": ("ARBORA-ACCEPTANCE-R006.2", "Reliable and inspectable loop"),
    "P3": ("ARBORA-ACCEPTANCE-R006.3", "Boundaries hold with several agents"),
    "P4": ("ARBORA-ACCEPTANCE-R006.4", "Cross-modal bet and memory maintenance"),
}
REMAINING = ("P5", "Every other family")
ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R\d+(?:\.\d+)*\b")


def named_ids(text: str, own: str) -> list[str]:
    """Requirement IDs a scenario row names, in order, without the row itself."""
    return list(dict.fromkeys(i for i in ID_RE.findall(text) if i != own))


def read_scenarios(workspace: Path, ref: str = "origin/main") -> dict[str, list[str]]:
    """Phase -> requirement IDs named by its scenario row."""
    proc = subprocess.run(
        ["git", "-C", str(workspace / SCENARIO_REPO), "show", f"{ref}:{SCENARIO_FILE}"],
        capture_output=True,
        text=True,
        check=False,
    )
    texts = requirement_text(proc.stdout)
    out = {}
    for phase, (sid, _name) in SCENARIOS.items():
        if sid not in texts:
            raise SystemExit(f"scenario row {sid} not found at {ref}:{SCENARIO_FILE}")
        out[phase] = named_ids(texts[sid], sid)
    return out


def closure(roots: list[str], depends: dict[str, list[str]]) -> set[str]:
    """The roots plus every row they transitively depend on (rows unknown to any repository stay, to be reported)."""
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        rid = stack.pop()
        if rid in seen:
            continue
        seen.add(rid)
        stack.extend(depends.get(rid, ()))
    return seen


def assign(scenarios: dict[str, list[str]], rows: dict[str, dict]) -> tuple[dict[str, list[str]], list[str]]:
    """Give each row to the earliest phase reaching it. Returns (phase -> row IDs, missing IDs)."""
    depends = {rid: r.get("depends_on", []) for rid, r in rows.items()}
    owner: dict[str, str] = {}
    for phase in SCENARIOS:
        for rid in sorted(closure(scenarios[phase], depends)):
            owner.setdefault(rid, phase)
    missing = sorted(rid for rid in owner if rid not in rows)
    by_phase: dict[str, list[str]] = {p: [] for p in SCENARIOS}
    for rid, phase in owner.items():
        if rid in rows:
            by_phase[phase].append(rid)
    return by_phase, missing


def manifest(phase: str, ids: list[str], rows: dict[str, dict]) -> dict:
    """One release manifest: identity plus scope entries grouped by repository and spec."""
    sid, name = SCENARIOS[phase]
    grouped: dict[tuple[str, str], list[str]] = {}
    for rid in sorted(ids):
        r = rows[rid]
        grouped.setdefault((r["repo"], r.get("spec_id") or r["family"].upper()), []).append(rid)
    scope = [{"repo": repo, "spec": spec, "roots": roots} for (repo, spec), roots in sorted(grouped.items())]
    return {"id": phase, "name": name, "phase": phase, "scenario": sid, "scope": scope}


def remaining_manifest() -> dict:
    phase, name = REMAINING
    return {"id": phase, "name": name, "phase": phase, "scenario": "none", "scope": "all-remaining"}


def write(releases: dict[str, dict], directory: Path) -> None:
    directory.mkdir(exist_ok=True)
    for rid, doc in releases.items():
        (directory / f"{rid}.yml").write_text(json.dumps(doc, indent=1) + "\n")


def load_manifests(directory: Path) -> list[dict]:
    """Every ``*.yml`` manifest in the directory, ordered by release ID."""
    return [json.loads(p.read_text()) for p in sorted(directory.glob("*.yml"))]


def scoped_ids(doc: dict) -> list[str]:
    if doc.get("scope") == "all-remaining":
        return []
    return [rid for entry in doc["scope"] for rid in entry["roots"]]


def check(manifests: list[dict], rows: dict[str, dict]) -> list[str]:
    """Findings: a row in two releases, a scope row no repository declares, or a scope entry that mismatches its row."""
    owner: dict[str, str] = {}
    problems: list[str] = []
    for doc in manifests:
        if doc.get("scope") == "all-remaining":
            continue
        for entry in doc["scope"]:
            for rid in entry["roots"]:
                if rid not in rows:
                    problems.append(f"{doc['id']}: row {rid} is not declared by any repository")
                elif rid in owner and owner[rid] != doc["id"]:
                    problems.append(f"{rid}: in both {owner[rid]} and {doc['id']}")
                elif rows[rid]["repo"] != entry["repo"]:
                    problems.append(f"{doc['id']}: row {rid} belongs to {rows[rid]['repo']}, not {entry['repo']}")
                owner.setdefault(rid, doc["id"])
    return problems


def all_rows(workspace: Path) -> dict[str, dict]:
    registry = json.loads(REGISTRY.read_text())["repositories"]

    def one(entry: dict):
        # The registry's local paths predate some renames; fall back to the flat checkout of the same name.
        for rel in (entry["local"], f"agent-packages/{entry['name']}", f"agent-packages/agents/{entry['name']}"):
            if (workspace / rel / ".git").exists():
                entry = {**entry, "local": rel}
                break
        try:
            return snapshot(entry, "local", workspace, None)
        except subprocess.CalledProcessError:  # a registered repository with no local clone
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        snaps = [s for s in pool.map(one, registry) if s]
    return {r["id"]: r for s in snaps for r in s.rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--scenario-ref", default="origin/main", help="arbora ref that holds the scenario rows")
    ap.add_argument("--releases", type=Path, default=RELEASES)
    ap.add_argument("--check", action="store_true", help="validate the committed manifests instead of writing")
    args = ap.parse_args(argv)
    rows = all_rows(args.workspace)
    if args.check:
        problems = check(load_manifests(args.releases), rows)
        for p in problems:
            print(p, file=sys.stderr)
        return 1 if problems else 0
    by_phase, missing = assign(read_scenarios(args.workspace, args.scenario_ref), rows)
    for rid in missing:
        print(f"warning: dependency {rid} is declared by no repository and stays out of scope", file=sys.stderr)
    releases = {p: manifest(p, ids, rows) for p, ids in by_phase.items()}
    releases[REMAINING[0]] = remaining_manifest()
    write(releases, args.releases)
    for p, ids in by_phase.items():
        print(f"{p}: {len(ids)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
