"""Strict opt-in producer. Legacy snapshots are deliberately not silently upgraded."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from networkx import DiGraph, strongly_connected_components
from pathlib import Path

from pipelines_hooks.specs.priority import Node, frontier, score

from .story_activity import validate as validate_activity

SCHEMA = "architecture-story/1"
STATUSES = ("VERIFIED", "LANDED", "SPECIFIED", "RETIRED")
FORMULA = "goal-weighted/1"


class ContractError(ValueError):
    """Required evidence is missing or inconsistent; do not promote output."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def provenance(value: dict) -> None:
    require(isinstance(value, dict), "missing provenance")
    require(set(value) == {"repository", "commit", "path", "fragment"}, "unexpected provenance fields")
    require(bool(re.fullmatch(r"[^/\s]+/[^/\s]+", value.get("repository", ""))), "source repository required")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", value.get("commit", ""))), "full source SHA required")
    require(
        all(isinstance(value.get(k), str) and value[k].strip() for k in ("path", "fragment")),
        "source location required",
    )


def mapping(value: dict, *, allow_na: bool = False) -> list:
    require(isinstance(value, dict), "missing reviewed mapping")
    require(set(value) <= {"state", "keys", "provenance", "reason"}, "unexpected mapping fields")
    provenance(value.get("provenance"))
    state, keys = value.get("state"), value.get("keys")
    if "reason" in value:
        require(isinstance(value["reason"], str) and bool(value["reason"].strip()), "invalid mapping reason")
    require(
        isinstance(keys, list)
        and all(isinstance(k, str) and k.strip() and k == k.strip() for k in keys)
        and len(keys) == len(set(keys)),
        "invalid mapping keys",
    )
    require(
        state == "complete"
        and bool(keys)
        or state in ({"none_declared", "not_applicable"} if allow_na else {"none_declared"})
        and not keys
        and bool(value.get("reason")),
        "invalid mapping applicability",
    )
    return keys


def validate_source_evidence(value: dict) -> None:
    require(
        isinstance(value, dict)
        and set(value)
        == {"status", "landedIn", "verifiedBy", "rollupOf", "placements", "declaredDependencyIds", "dependencyContext"},
        "malformed source evidence",
    )
    provenance(value["status"])
    require(isinstance(value["dependencyContext"], list), "invalid dependency context")
    for context in value["dependencyContext"]:
        require(
            isinstance(context, dict)
            and set(context) == {"kind", "text", "tokens"}
            and context["kind"]
            in {"requirement_prerequisites", "non_requirement_context", "ignored_self_reference", "repeated_reference"}
            and isinstance(context["text"], str)
            and isinstance(context["tokens"], list)
            and all(isinstance(token, str) for token in context["tokens"]),
            "invalid typed dependency context",
        )
    for field in ("landedIn", "verifiedBy", "rollupOf", "declaredDependencyIds"):
        require(
            isinstance(value[field], list) and all(isinstance(v, str) and v.strip() for v in value[field]),
            "invalid source evidence list",
        )
    require(isinstance(value["placements"], list) and bool(value["placements"]), "placement evidence required")
    for placement in value["placements"]:
        require(
            isinstance(placement, dict)
            and set(placement) == {"nodeId", "provenance"}
            and isinstance(placement["nodeId"], str)
            and bool(placement["nodeId"].strip()),
            "invalid placement evidence",
        )
        provenance(placement["provenance"])


def validate_model_evidence(value, node_ids, repo_ids):
    require(
        isinstance(value, dict) and set(value) == {"provenance", "interfaces", "references", "code"},
        "invalid model evidence",
    )
    provenance(value["provenance"])
    require(isinstance(value["interfaces"], list), "invalid model interfaces")
    for edge in value["interfaces"]:
        require(
            isinstance(edge, list)
            and len(edge) == 3
            and edge[0] in node_ids
            and edge[1] in node_ids
            and isinstance(edge[2], str)
            and bool(edge[2].strip()),
            "invalid model interface endpoints/label",
        )
    require(
        isinstance(value["references"], list) and all(ref in node_ids for ref in value["references"]),
        "invalid nondirectional model reference",
    )
    require(isinstance(value["code"], list), "invalid model code evidence")
    for code in value["code"]:
        require(
            isinstance(code, dict)
            and set(code) == {"repositoryId", "path", "commit", "state", "linkable", "reason", "requirementKeys"}
            and code["repositoryId"] in repo_ids
            and code["state"] in {"existing", "planned"}
            and type(code["linkable"]) is bool
            and code["linkable"] == (code["state"] == "existing")
            and isinstance(code["reason"], str)
            and isinstance(code["requirementKeys"], list)
            and isinstance(code["path"], str)
            and bool(code["path"].strip())
            and bool(re.fullmatch(r"[0-9a-f]{40}", code["commit"])),
            "invalid model code provenance",
        )


def cycle_groups(rows):
    """Declared SCC diagnostics only; the existing scorer/frontier remain authoritative."""
    graph = DiGraph()
    graph.add_nodes_from(row["key"] for row in rows)
    graph.add_edges_from((row["key"], target) for row in rows for target in row["dependencies"]["keys"])
    return sorted(
        (sorted(group) for group in strongly_connected_components(graph) if len(group) > 1), key=lambda group: group[0]
    )


def produce(
    *,
    nodes: list[dict],
    rows: list[dict],
    repositories: list[dict],
    activity: dict,
    built_at: str,
    max_age_seconds: int,
) -> dict:
    """Validate entire input and return an allowlisted, JSON-safe story export.

    Relationships here are reviewed interface/reference evidence, never converted
    into requirement dependencies. Inputs require explicit canonical row targets.
    """
    try:
        return _produce(nodes, rows, repositories, activity, built_at, max_age_seconds)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ContractError("malformed required story input") from exc


def _produce(nodes, rows, repositories, activity, built_at, max_age_seconds):
    require(
        all(isinstance(r["id"], str) and r["id"].strip() and r["id"] == r["id"].strip() for r in repositories),
        "invalid repository identity",
    )
    repos = {r["id"]: r for r in repositories}
    require(bool(repos) and len(repos) == len(repositories), "empty or duplicate repository identities")
    require(len({r["fullName"] for r in repositories}) == len(repositories), "duplicate canonical repository name")
    for repo in repositories:
        require(bool(re.fullmatch(r"[^/\s]+/[^/\s]+", repo["fullName"])), "invalid repository full name")
        require(repo["url"] == "https://github.com/" + repo["fullName"], "noncanonical repository URL")
        validate_activity(activity[repo["id"]], repo, built_at, max_age_seconds)
    indexed = {r["key"]: r for r in rows}
    require(len(indexed) == len(rows), "duplicate canonical row identity")
    # Shared scorer uses bare IDs, so reject collisions rather than silently merge.
    require(len({r["id"] for r in rows}) == len(rows), "ambiguous bare row IDs")
    by_id, exported = {}, {}
    for key, row in indexed.items():
        require(
            row["repositoryId"] in repos and key == row["repositoryId"] + ":" + row["id"], "noncanonical row identity"
        )
        require(row["status"] in STATUSES, "invalid delivery state")
        require(
            all(isinstance(row[k], str) and row[k].strip() for k in ("id", "title", "family")), "empty row description"
        )
        require(type(row["functional"]) is bool and type(row["rollup"]) is bool, "explicit row semantics required")
        provenance(row["provenance"])
        provenance(row["placement"])
        require(
            row["provenance"]["repository"] == repos[row["repositoryId"]]["fullName"], "row source ownership mismatch"
        )
        targets = mapping(row["dependencies"])
        require(all(t in indexed and t != key for t in targets), "dangling or self dependency")
        by_id[row["id"]] = Node(
            row["id"],
            row["repositoryId"],
            row["status"],
            tuple(indexed[t]["id"] for t in targets),
            row["functional"],
            row["rollup"],
            row["title"],
        )
        exported[key] = {
            k: row[k]
            for k in (
                "key",
                "id",
                "title",
                "repositoryId",
                "status",
                "family",
                "rollup",
                "provenance",
                "placement",
                "dependencies",
            )
        }
    for key, row in indexed.items():
        if "sourceEvidence" in row:
            validate_source_evidence(row["sourceEvidence"])
            require(
                row["sourceEvidence"]["status"]["repository"] == row["provenance"]["repository"]
                and row["sourceEvidence"]["status"]["commit"] == row["provenance"]["commit"],
                "status and requirement source freeze mismatch",
            )
            require(set(row["sourceEvidence"]["rollupOf"]) <= indexed.keys(), "dangling rollup source evidence")
            require(
                row["sourceEvidence"]["status"]["fragment"] == row["id"]
                and row["sourceEvidence"]["status"]["path"] == "specs/" + row["family"] + "/status.json",
                "status evidence does not identify this row/family",
            )
            require(
                bool(row["sourceEvidence"]["rollupOf"]) == row["rollup"], "rollup evidence does not match row semantics"
            )
            exported[key]["sourceEvidence"] = row["sourceEvidence"]
    canonical = {r["id"]: r["key"] for r in rows}
    scores, ready = score(by_id), set(frontier(by_id, unknown_blocks=True))
    for key, row in indexed.items():
        scored = scores.get(row["id"])
        priority = {
            "state": "not_applicable",
            "formulaVersion": FORMULA,
            "reason": "delivery state is excluded by the scoring formula (no longer open)",
            "inputs": {},
        }
        if scored is not None:
            priority = {
                "state": "scored",
                "value": scored["priority"],
                "formulaVersion": FORMULA,
                "inputs": {
                    "competencyQuestions": [canonical[cq] for cq in scored["cqs"]],
                    "openDependents": scored["unblocks"],
                    "functionalFactor": 1 if row["functional"] else 0.5,
                },
            }
        exported[key]["priority"] = priority
        exported[key]["readiness"] = (
            "notApplicable"
            if row["status"] != "SPECIFIED" or row["rollup"]
            else "ready"
            if row["id"] in ready
            else "blocked"
        )
    require(
        all(isinstance(n["id"], str) and n["id"].strip() and n["id"] == n["id"].strip() for n in nodes),
        "invalid node identity",
    )
    node_index = {n["id"]: n for n in nodes}
    require(bool(nodes) and len(node_index) == len(nodes), "empty or duplicate node identity")
    require(sum(n["parentId"] is None for n in nodes) == 1, "exactly one root required")
    for row in rows:
        if "sourceEvidence" in row:
            require(
                all(p["nodeId"] in node_index for p in row["sourceEvidence"]["placements"]),
                "source evidence references unknown placement node",
            )
    for node in nodes:
        if "modelEvidence" in node:
            validate_model_evidence(node["modelEvidence"], node_index, repos)
    own, children = {}, {n["id"]: [] for n in nodes}
    for node in nodes:
        nid, parent = node["id"], node["parentId"]
        require(parent is None or parent in node_index and parent != nid, "invalid containment")
        if parent is not None:
            children[parent].append(nid)
        require(node["kind"] in {"internal_leaf", "aggregate", "external"}, "invalid node kind")
        for field in ("label", "purpose"):
            require(
                isinstance(node[field]["text"], str) and bool(node[field]["text"].strip()), "missing node description"
            )
            require(set(node[field]) == {"text", "provenance"}, "unexpected description fields")
            provenance(node[field]["provenance"])
        own[nid] = set(mapping(node["specs"], allow_na=True))
        require(own[nid] <= indexed.keys(), "unmapped spec identity")
        relationships = mapping(node["relationships"], allow_na=True)
        require(all(target in node_index for target in relationships), "dangling relationship")
        owners = mapping(node["ownership"], allow_na=True)
        require(set(owners) <= repos.keys(), "unknown repository owner")
        if node["kind"] == "external":
            require(
                not own[nid]
                and not owners
                and node["specs"]["state"] == "not_applicable"
                and node["ownership"]["state"] == "not_applicable",
                "external node requires explicit nonapplicability",
            )
        elif node["kind"] == "internal_leaf":
            require(len(owners) == 1, "leaf requires one canonical owner")
        require(all(indexed[k]["repositoryId"] in owners for k in own[nid]), "row placement ownership mismatch")
    for key, row in indexed.items():
        if "sourceEvidence" in row:
            places = row["sourceEvidence"]["placements"]
            expected = {nid for nid in own if key in own[nid]}
            require(
                len(places) == len(expected) and {place["nodeId"] for place in places} == expected,
                "placement evidence differs from actual reviewed bindings",
            )
            require(
                all(place["provenance"] == node_index[place["nodeId"]]["specs"]["provenance"] for place in places),
                "placement evidence provenance differs from reviewed mapping",
            )
    visited, result = set(), {}

    def visit(nid, path):
        require(nid not in path, "containment cycle")
        if nid in visited:
            return
        node, members, owners = node_index[nid], set(own[nid]), set(node_index[nid]["ownership"]["keys"])
        require((node["kind"] == "aggregate") == bool(children[nid]), "node kind/containment mismatch")
        for child in children[nid]:
            visit(child, path | {nid})
            members.update(result[child]["subtreeRows"])
            owners.update(result[child]["repositoryIds"])
        if node["kind"] == "aggregate":
            derived = {indexed[k]["repositoryId"] for k in own[nid]}
            for child in children[nid]:
                derived.update(result[child]["repositoryIds"])
            require(owners == derived, "aggregate ownership exceeds descendant evidence")
        counts = Counter(indexed[k]["status"] for k in members)
        readiness = Counter(exported[k]["readiness"] for k in members)
        top = sorted(
            (k for k in members if exported[k]["priority"]["state"] == "scored"),
            key=lambda k: (-exported[k]["priority"]["value"], k),
        )[:5]
        result[nid] = {
            "nodeId": nid,
            "parentId": node["parentId"],
            "kind": node["kind"],
            "label": node["label"],
            "purpose": node["purpose"],
            "specs": node["specs"],
            "relationships": node["relationships"],
            "ownership": node["ownership"],
            "ownRows": sorted(own[nid]),
            "subtreeRows": sorted(members),
            "statusCounts": {s: counts[s] for s in STATUSES},
            "families": dict(
                sorted(Counter(indexed[k]["repositoryId"] + ":" + indexed[k]["family"] for k in members).items())
            ),
            "readiness": {s: readiness[s] for s in ("ready", "blocked", "notApplicable")},
            "topPriorities": [{"rowKey": k, **exported[k]["priority"]} for k in top],
            "dependencyEdges": [
                {"source": k, "target": t, "provenance": indexed[k]["dependencies"]["provenance"]}
                for k in sorted(members)
                for t in indexed[k]["dependencies"]["keys"]
            ],
            "repositoryIds": sorted(owners),
            "activityRefs": sorted(owners),
            "repositoryActivity": {
                field: sum(activity[r][field] for r in owners) for field in ("openPullRequests", "openIssues")
            },
        }
        if "modelEvidence" in node:
            require(
                all(code["repositoryId"] in owners for code in node["modelEvidence"]["code"]),
                "code evidence outside canonical node ownership",
            )
            for code in node["modelEvidence"]["code"]:
                if code["state"] == "planned":
                    require(
                        bool(code["requirementKeys"])
                        and set(code["requirementKeys"]) == own[nid]
                        and all(indexed[key]["status"] == "SPECIFIED" for key in code["requirementKeys"]),
                        "planned code needs nonempty reviewed SPECIFIED scope",
                    )
            result[nid]["modelEvidence"] = node["modelEvidence"]
        visited.add(nid)

    for nid in node_index:
        visit(nid, set())
    require(set().union(*own.values()) == indexed.keys(), "rows without reviewed placement")
    # Round-trip detaches caller-owned nested values. Never export request/token inputs.
    return json.loads(
        json.dumps(
            {
                "schemaVersion": SCHEMA,
                "builtAt": built_at,
                "dependencyCycles": [
                    {
                        "rowKeys": group,
                        "openRowKeys": [key for key in group if indexed[key]["status"] == "SPECIFIED"],
                        "readyRowKeys": [key for key in group if exported[key]["readiness"] == "ready"],
                        "blockedRowKeys": [key for key in group if exported[key]["readiness"] == "blocked"],
                        "provenance": [indexed[key]["dependencies"]["provenance"] for key in group],
                    }
                    for group in cycle_groups(rows)
                ],
                "nodes": result,
                "rows": exported,
                "repositories": {r: {k: repos[r][k] for k in ("id", "fullName", "url")} for r in repos},
                "activity": {
                    r: {
                        k: activity[r][k]
                        for k in (
                            "repositoryId",
                            "fullName",
                            "observedAt",
                            "lastVerifiedAt",
                            "attemptedAt",
                            "freshness",
                            "refreshOutcome",
                            "failureCategory",
                            "openPullRequests",
                            "openIssues",
                            "queryVersion",
                            "integrity",
                        )
                    }
                    for r in repos
                },
            }
        )
    )


def export_atomic(destination: Path, **inputs) -> dict:
    """Validate first; replace one complete JSON artifact, never a partial payload."""
    payload = produce(**inputs)
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return payload
