"""Derive release bundle manifests from the phase scenarios (PIPE-RELEASE-R021).

Each phase scenario row (``ARBORA-ACCEPTANCE-R006.1`` to ``.4``) names the requirement rows it exercises. A phase's
scope is those rows plus the transitive closure of their ``Depends:`` rows across every registered repository. A
row belongs to the earliest phase that reaches it. Phase P5 takes every remaining row.

Manifests are written to ``releases/<id>.yml`` as JSON, which is valid YAML, so no YAML library is needed.

Usage:
  python scripts/release_scope.py --workspace /path/to/workspace            # write releases/
  python scripts/release_scope.py --workspace /path/to/workspace --check    # fail on a duplicate or missing row
  python scripts/release_scope.py --workspace W --plan P1 [--gate ...]      # one bundle plan; BUNDLE_CYCLE refuses
  python scripts/release_scope.py --workspace W --exit-gates                # resolve the program exit gates table
"""

from __future__ import annotations

import argparse
import heapq
import json
import os
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
    "P5": ("ARBORA-ACCEPTANCE-R006.7", "Answers across connectors and virtual graphs"),
}
# Rows that no scenario holds stay in the last phase (PIPE-RELEASE-R023).
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


def depends_map(rows: dict[str, dict]) -> dict[str, list[str]]:
    """Closure edges: ``Depends:`` rows plus the provider and consumer rows of contracts (PIPE-RELEASE-R025.1)."""
    return {
        rid: [*r.get("depends_on", []), *r.get("provided_by", []), *r.get("consumed_by", [])] for rid, r in rows.items()
    }


def assign(scenarios: dict[str, list[str]], rows: dict[str, dict]) -> tuple[dict[str, list[str]], list[str]]:
    """Give each row to the earliest phase reaching it. Returns (phase -> row IDs, missing IDs)."""
    depends = depends_map(rows)
    owner: dict[str, str] = {}
    for phase in SCENARIOS:
        for rid in sorted(closure(scenarios.get(phase, []), depends)):
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
    doc = {"id": phase, "name": name, "phase": phase, "scenario": sid, "scope": scope}
    if phase == REMAINING[0]:
        doc["rest"] = "all-remaining"
    return doc


def remaining_manifest() -> dict:
    """The manifest of rows no phase holds (a release with no scenario of its own)."""
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


class BundleCycle(ValueError):
    """A dependency cycle among repositories (PIPE-RELEASE-R025.3); names the repositories and the rows on it."""

    def __init__(self, repos: list[str], rows: list[str]) -> None:
        self.repos, self.rows = repos, rows
        super().__init__(f"BUNDLE_CYCLE: {' -> '.join([*repos, repos[0]])} (rows {', '.join(rows)})")


def _repo_edges(ids: set[str], rows: dict[str, dict]) -> dict[tuple[str, str], tuple[str, str]]:
    """``(earlier repository, later repository)`` -> one ``(earlier row, later row)`` that forces the order."""
    edges: dict[tuple[str, str], tuple[str, str]] = {}
    for rid in sorted(ids):
        for dep in [*rows[rid].get("depends_on", []), *rows[rid].get("provided_by", [])]:
            if dep in ids and dep in rows and rows[dep]["repo"] != rows[rid]["repo"]:
                edges.setdefault((rows[dep]["repo"], rows[rid]["repo"]), (dep, rid))
    return edges


def _cycle(edges: dict[tuple[str, str], tuple[str, str]], stuck: set[str]) -> tuple[list[str], list[str]]:
    """One cycle among the repositories Kahn's sort could not place, with a row on each edge of it."""
    before = {b: a for (a, b) in sorted(edges) if a in stuck and b in stuck}
    node, seen = sorted(stuck)[0], []
    while node not in seen:
        seen.append(node)
        node = before[node]
    loop = seen[seen.index(node) :][::-1]
    pairs = [(loop[i], loop[(i + 1) % len(loop)]) for i in range(len(loop))]
    return loop, sorted({row for pair in pairs for row in edges[pair]})


def train_order(ids: set[str], rows: dict[str, dict]) -> list[str]:
    """Repositories of a closure in dependency order, ties by name; no repository name is written in code."""
    edges = _repo_edges(ids, rows)
    repos = {rows[rid]["repo"] for rid in ids if rid in rows}
    waiting = {r: 0 for r in repos}
    after: dict[str, list[str]] = {r: [] for r in repos}
    for before, later in edges:
        waiting[later] += 1
        after[before].append(later)
    ready = [r for r, n in waiting.items() if n == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        repo = heapq.heappop(ready)
        order.append(repo)
        for later in after[repo]:
            waiting[later] -= 1
            if waiting[later] == 0:
                heapq.heappush(ready, later)
    if len(order) < len(repos):
        raise BundleCycle(*_cycle(edges, repos - set(order)))
    return order


def bundle_closure(doc: dict, rows: dict[str, dict]) -> set[str]:
    """Every known row in the dependency closure of a bundle's scoped rows, across repositories."""
    return {rid for rid in closure(scoped_ids(doc), depends_map(rows)) if rid in rows}


def bundle_gate(
    doc: dict, rows: dict[str, dict], plan: dict, scenario_runs: dict, reach: dict[str, bool] | None = None
) -> list[str]:
    """``BUNDLE_NOT_DELIVERED`` findings (PIPE-RELEASE-R020): a scoped row that is not delivered, or a phase scenario
    whose latest run did not pass. Empty when the bundle may be cut."""
    from scripts.release_delivered import open_rows

    run = scenario_runs.get(doc["scenario"])
    scoped = [rid for rid in scoped_ids(doc) if rid in plan["closure"]]
    found = [f"BUNDLE_NOT_DELIVERED: {rid}: {why}" for rid, why in open_rows(scoped, rows, reach or {}, run).items()]
    if not run or not run.get("passed"):
        found.append(f"BUNDLE_NOT_DELIVERED: scenario {doc['scenario']} has no passing run")
    return found


PHASES = tuple(SCENARIOS)
GATES_HEADING = "### Program exit gates"
FINAL_SCENARIO = "ARBORA-ACCEPTANCE-R006.8"
CHANNELS = ("web", "messaging")


def gate_table(plan_text: str) -> list[dict]:
    """The rows of the table under ``### Program exit gates``: gate, row IDs and phase text."""
    section = plan_text.partition(GATES_HEADING)[2].split("\n## ")[0].split("\n### ")[0]
    out = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) >= 3 and cells[0] not in ("Gate",) and not set(cells[0]) <= {"-"}:
            out.append({"gate": cells[0], "rows": ID_RE.findall(cells[1]), "phase": cells[2]})
    return out


def exit_gates(plan_text: str, rows: dict[str, dict], owners: set[str]) -> list[str]:
    """Findings of the exit gates table (PIPE-RELEASE-R026.1): a gate with no row, an undefined row, a phase outside
    P1 to P5, or a row whose repository is not in the owner map."""
    gates = gate_table(plan_text)
    if not gates:
        return [f"no gate table under '{GATES_HEADING}'"]
    problems = []
    for g in gates:
        if not g["rows"]:
            problems.append(f"{g['gate']}: names no row")
        problems += [f"{g['gate']}: row {rid} is defined by no spec" for rid in g["rows"] if rid not in rows]
        problems += [
            f"{g['gate']}: row {rid} belongs to {rows[rid]['repo']}, which is not in the owner map"
            for rid in g["rows"]
            if rid in rows and rows[rid]["repo"] not in owners
        ]
        phases = re.findall(r"\bP\d+\b", g["phase"])
        if not phases or any(p not in PHASES for p in phases):
            problems.append(f"{g['gate']}: phase '{g['phase']}' is outside P1 to P5")
    return problems


def connector_gate(
    rows: dict[str, dict], connectors: set[str], reach: dict[str, bool], run: dict | None, report: dict
) -> list[str]:
    """PIPE-RELEASE-R026.2: every connector spec row delivered and every fixture connector ready."""
    from scripts.release_delivered import open_rows

    ids = [rid for rid, r in rows.items() if r["repo"] in connectors]
    found = [f"open row {rid}: {why}" for rid, why in open_rows(ids, rows, reach, run).items()]
    found += [
        f"connector {name} is not ready"
        for name, state in sorted(report.get("connectors", {}).items())
        if not state.get("ready")
    ]
    return found


def channel_gate(scenario_runs: dict) -> list[str]:
    """PIPE-RELEASE-R026.3: the vision questions passed through the web UI and a messaging channel."""
    channels = (scenario_runs.get(FINAL_SCENARIO) or {}).get("channels", {})
    return [f"channel {c} has no passing run" for c in CHANNELS if not channels.get(c, {}).get("passed")]


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
    rows = {r["id"]: r for s in snaps for r in s.rows}
    for provider, consumer in sorted({edge for s in snaps for edge in s.contracts}):
        if provider in rows and consumer in rows:
            rows[provider].setdefault("consumed_by", []).append(consumer)
            rows[consumer].setdefault("provided_by", []).append(provider)
    return rows


def _json(path: Path | None) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path else {}


def _plan_command(args: argparse.Namespace, rows: dict[str, dict]) -> int:
    from scripts.release_plan import facts_of, plan_bytes, publish_plan, render_plan

    docs = load_manifests(args.releases)
    doc = next((d for d in docs if d["id"] == args.plan), None)
    if doc is None:
        print(f"no release {args.plan}", file=sys.stderr)
        return 2
    try:
        for other in docs:  # a cycle across bundles refuses as well
            render_plan(other, rows)
        plan = render_plan(doc, rows)
    except BundleCycle as exc:
        print(exc, file=sys.stderr)  # nothing is written
        return 1
    sys.stdout.buffer.write(plan_bytes(plan))
    code = 0
    if args.gate:
        found = bundle_gate(doc, rows, plan, _json(args.scenario_runs), _json(args.reach))
        print("\n".join(found), file=sys.stderr)
        code = 1 if found else 0
    if args.publish:
        print(publish_plan(facts_of(plan, rows), plan, args.endpoint), file=sys.stderr)
    return code


def _exit_gates_command(args: argparse.Namespace, rows: dict[str, dict]) -> int:
    registry = json.loads(REGISTRY.read_text())["repositories"]
    problems = exit_gates(args.plan_file.read_text(encoding="utf-8"), rows, {r["name"] for r in registry})
    if args.final:
        runs = _json(args.scenario_runs)
        connectors = {r["name"] for r in registry if r.get("kind") == "connector"}
        problems += connector_gate(
            rows, connectors, _json(args.reach), runs.get(SCENARIOS["P5"][0]), _json(args.connector_report)
        )
        problems += channel_gate(runs)
    print("\n".join(problems), file=sys.stderr)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--scenario-ref", default="origin/main", help="arbora ref that holds the scenario rows")
    ap.add_argument("--releases", type=Path, default=RELEASES)
    ap.add_argument("--check", action="store_true", help="validate the committed manifests instead of writing")
    ap.add_argument("--plan", metavar="RELEASE", help="print the plan of one release; a repository cycle refuses")
    ap.add_argument("--gate", action="store_true", help="with --plan: stop with BUNDLE_NOT_DELIVERED on an open row")
    ap.add_argument("--publish", action="store_true", help="with --plan: post the release graph to the endpoint")
    ap.add_argument("--endpoint", default=os.environ.get("ARBORA_SOURCE_URL", ""), help="arbora source.* endpoint")
    ap.add_argument("--scenario-runs", type=Path, help="JSON: scenario ID -> latest recorded run")
    ap.add_argument("--reach", type=Path, help="JSON: row ID -> reachable from a production caller")
    ap.add_argument("--exit-gates", action="store_true", help="resolve the program exit gates table of the plan")
    ap.add_argument("--plan-file", type=Path, default=ROOT / "specs/ordered-digest-release/plan.md")
    ap.add_argument("--final", action="store_true", help="with --exit-gates: also hold the program final gates")
    ap.add_argument("--connector-report", type=Path, help="JSON: the ephemeral stack's connector readiness")
    args = ap.parse_args(argv)
    rows = all_rows(args.workspace)
    if args.exit_gates:
        return _exit_gates_command(args, rows)
    if args.plan:
        return _plan_command(args, rows)
    if args.check:
        problems = check(load_manifests(args.releases), rows)
        for p in problems:
            print(p, file=sys.stderr)
        return 1 if problems else 0
    by_phase, missing = assign(read_scenarios(args.workspace, args.scenario_ref), rows)
    for rid in missing:
        print(f"warning: dependency {rid} is declared by no repository and stays out of scope", file=sys.stderr)
    releases = {p: manifest(p, ids, rows) for p, ids in by_phase.items()}
    try:
        for doc in releases.values():
            train_order(bundle_closure(doc, rows), rows)
    except BundleCycle as exc:
        print(exc, file=sys.stderr)  # no partial plan is written
        return 1
    write(releases, args.releases)
    for p, ids in by_phase.items():
        print(f"{p}: {len(ids)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
