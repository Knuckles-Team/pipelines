"""Source-only chart evidence: no canvas mapping, activity defaults, or publication."""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections import Counter
from copy import deepcopy
from pathlib import Path

from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.specs.aliases import canonical_id, retired_prefix, validate_alias_document
from pipelines_hooks.specs.priority import Node, frontier, score
from pipelines_hooks.specs.generator import generate_at, render
from pipelines_hooks.specs.requirements_doc import parse_rows

from .story_contract import FORMULA, STATUSES, cycle_groups, provenance, require
from .story_sources import normalize_family, source_ref

# Requirement ID prefixes owned by organization repositories (the routing table in
# reference/ecosystem-boundaries.md).
ORGANIZATION_SPEC_PREFIXES = frozenset(
    {"ARBORA", "AXIL", "CONN", "EMERALD", "MEDULLA", "MERISTEM", "OVERSTORY", "PIPE", "SCION", "TUIG", "US"}
)


def capture_git(root: Path, commit: str, repository: dict) -> dict:
    """Read exactly one existing full Git commit; no fetch, ref fallback, or API."""
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "full frozen commit required")
    git_env = sanitized_env()

    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], env=git_env, check=True, capture_output=True).stdout

    require(git("rev-parse", commit + "^{commit}").decode().strip() == commit, "commit resolution mismatch")
    entries = git("ls-tree", "-r", "-z", commit).split(b"\0")
    paths = []
    documents = {}
    for entry in entries:
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, kind, _oid = header.split()
        path = raw_path.decode("utf-8")
        if kind != b"blob":
            continue
        paths.append(path)
        if path == ".config/spec-aliases.toml" or re.fullmatch(r"specs/[^/]+/requirements\.md", path):
            require(mode != b"120000", "source document may not be a symlink: " + path)
            documents[path] = git("show", f"{commit}:{path}").decode("utf-8")
    # status.json is never committed: compute it at this commit and present it as a source document.
    for path, document in generate_at(str(root), commit).items():
        if path not in paths:
            paths.append(path)
        documents[path] = render(document)
    return {
        "repositoryId": repository["id"],
        "head": commit,
        "tree": {"truncated": False, "paths": paths},
        "documents": documents,
    }


def source_chart(
    *,
    captures: list[dict],
    repositories: list[dict],
    selection: list[str],
    score_scope: str = "complete-captured-repositories",
) -> dict:
    """Complete captured-repository denominator; selection is canonical family keys.

    Missing dependency closure rejects the entire view. Scores cover the supplied
    complete repositories, not unscanned fleet dependents. No model binding is
    inferred from a family or repository identity.
    """
    require(
        score_scope in {"complete-captured-repositories", "selected-family-prerequisite-closure"}, "invalid score scope"
    )
    repos = {r["id"]: r for r in repositories}
    require(bool(repos) and len(repos) == len(repositories), "duplicate/empty repository scope")
    require(len({r["fullName"] for r in repositories}) == len(repositories), "duplicate repository name")
    for rid, repo in repos.items():
        require(isinstance(rid, str) and bool(rid.strip()) and rid == rid.strip(), "invalid repository ID")
        require(bool(re.fullmatch(r"[^/\s]+/[^/\s]+", repo["fullName"])), "invalid canonical full name")
        require(repo["url"] == "https://github.com/" + repo["fullName"], "invalid repository URL")
    require(
        len(captures) == len(repos) and {c["repositoryId"] for c in captures} == set(repos), "capture scope mismatch"
    )
    rows, aliases, freezes = [], {}, []
    for capture in captures:
        repo = repos[capture["repositoryId"]]
        commit, tree, docs = capture["head"], capture["tree"], capture["documents"]
        provenance(source_ref(repo["fullName"], commit, "specs", "complete inventory"))
        paths = tree["paths"]
        require(
            tree["truncated"] is False and isinstance(paths, list) and len(paths) == len(set(paths)), "incomplete tree"
        )
        require(
            all(isinstance(p, str) and p and not p.startswith("/") and ".." not in p.split("/") for p in paths),
            "unsafe source path",
        )
        families = sorted(
            {p.split("/")[1] for p in paths if re.fullmatch(r"specs/(?!_)[^/]+/(requirements\.md|status\.json)", p)}
        )
        require(bool(families), "empty source families")
        current, active = set(), set()
        for family in families:
            req, status = f"specs/{family}/requirements.md", f"specs/{family}/status.json"
            require(
                all(p in paths and isinstance(docs.get(p), str) and docs[p].strip() for p in (req, status)),
                "missing source pair: " + family,
            )
            rows.extend(
                normalize_family(
                    repository=repo, commit=commit, family=family, markdown=docs[req], status_text=docs[status]
                )
            )
            parsed = parse_rows(docs[req])
            current.update(r.id for r in parsed)
            active.update(r.id for r in parsed if r.retired_reason is None)
        alias_path = ".config/spec-aliases.toml"
        raw_aliases = {}
        if alias_path in paths:
            require(isinstance(docs.get(alias_path), str), "missing alias capture")
            raw_aliases = validate_alias_document(
                tomllib.loads(docs[alias_path]), current_ids=current, active_ids=active, source_path=Path(alias_path)
            )
        aliases[repo["id"]] = (raw_aliases, source_ref(repo["fullName"], commit, alias_path, "aliases"))
        freezes.append(
            {"repositoryId": repo["id"], "fullName": repo["fullName"], "commit": commit, "families": families}
        )
    indexed = {r["id"]: r for r in rows}
    require(len(indexed) == len(rows), "ambiguous bare requirement IDs in score scope")
    # A prerequisite owned by a known organization repository outside the
    # capture is an external reference, not a gap. Captured and unknown
    # prefixes must still resolve.
    captured_prefixes = {r["id"].split("-", 1)[0] for r in rows}
    external_prefixes = ORGANIZATION_SPEC_PREFIXES - captured_prefixes
    dependency_gaps = []
    for row in rows:
        targets, resolutions = [], []
        for declared in row.pop("declaredDependencies"):
            candidates = []
            if declared in indexed:
                candidates.append((declared, None, None))
            for repo_id, (rules, ref) in aliases.items():
                resolved = canonical_id(declared, rules)
                if resolved != declared and resolved in indexed and indexed[resolved]["repositoryId"] == repo_id:
                    require(indexed[resolved]["status"] != "RETIRED", "alias target is retired: " + resolved)
                    candidates.append((resolved, ref, retired_prefix(declared, rules)))
            if not candidates and declared.split("-", 1)[0] in external_prefixes:
                row.setdefault("externalDependencies", []).append(declared)
                continue
            if len(candidates) != 1:
                dependency_gaps.append(
                    {
                        "rowKey": row["key"],
                        "declaredId": declared,
                        "code": "unresolved_or_ambiguous_dependency",
                        "provenance": row["provenance"],
                        "context": row["sourceEvidence"]["dependencyContext"],
                    }
                )
                continue
            resolved, ref, matched = candidates[0]
            require(resolved != row["id"], "alias resolves prerequisite to self: " + row["id"])
            key = indexed[resolved]["key"]
            if key not in targets:
                targets.append(key)
            resolutions.append(
                {
                    "declaredId": declared,
                    "targetKey": key,
                    "aliasProvenance": ({**ref, "fragment": matched} if ref else None),
                    "matchedAliasKey": matched,
                }
            )
        row["dependencies"] = {"keys": targets, "provenance": row["provenance"], "resolutions": resolutions}
        row["sourceEvidence"]["rollupOf"] = [indexed[r]["key"] for r in row["sourceEvidence"]["rollupOf"]]
    by_key = {r["key"]: r for r in rows}
    family_keys = {r["repositoryId"] + ":" + r["family"] for r in rows}
    require(
        bool(selection) and len(selection) == len(set(selection)) and set(selection) <= family_keys,
        "invalid family selection",
    )
    selected = {r["key"] for r in rows if r["repositoryId"] + ":" + r["family"] in selection}
    closure, pending = set(selected), list(selected)
    while pending:
        for target in by_key[pending.pop()]["dependencies"]["keys"]:
            if target not in closure:
                closure.add(target)
                pending.append(target)
    captured_count = len(rows)
    scope_keys = set(by_key) if score_scope == "complete-captured-repositories" else closure
    relevant_gaps = [gap for gap in dependency_gaps if gap["rowKey"] in scope_keys]
    require(
        not relevant_gaps,
        "unresolved/ambiguous dependency: "
        + "; ".join(gap["rowKey"] + " -> " + gap["declaredId"] for gap in relevant_gaps),
    )
    rows = [r for r in rows if r["key"] in scope_keys]
    evidence_keys, pending_evidence = set(), list(scope_keys)
    while pending_evidence:
        for target in by_key[pending_evidence.pop()]["sourceEvidence"]["rollupOf"]:
            if target not in scope_keys and target not in evidence_keys:
                evidence_keys.add(target)
                pending_evidence.append(target)
    evidence_rows = {
        key: {
            **{
                field: by_key[key][field]
                for field in (
                    "key",
                    "id",
                    "repositoryId",
                    "family",
                    "title",
                    "status",
                    "rollup",
                    "provenance",
                    "sourceEvidence",
                )
            },
            "scopeRole": "rollup_evidence_only_not_scored",
        }
        for key in sorted(evidence_keys)
    }
    nodes = {
        r["id"]: Node(
            r["id"],
            r["repositoryId"],
            r["status"],
            tuple(by_key[k]["id"] for k in r["dependencies"]["keys"]),
            r["functional"],
            r["rollup"],
            r["title"],
        )
        for r in rows
    }
    scores, ready = score(nodes), set(frontier(nodes, unknown_blocks=True))
    for row in rows:
        value = scores.get(row["id"])
        row["priority"] = {
            "state": "not_applicable",
            "formulaVersion": FORMULA,
            "reason": "delivery state is excluded by the scoring formula (no longer open)",
            "inputs": {},
        }
        if value is not None:
            row["priority"] = {
                "state": "scored",
                "value": value["priority"],
                "formulaVersion": FORMULA,
                "inputs": {
                    "competencyQuestions": [indexed[r]["key"] for r in value["cqs"]],
                    "openDependents": value["unblocks"],
                    "functionalFactor": 1 if row["functional"] else 0.5,
                },
            }
        row["readiness"] = (
            "notApplicable"
            if row["status"] != "SPECIFIED" or row["rollup"]
            else "ready"
            if row["id"] in ready
            else "blocked"
        )
    families = []
    for family in sorted(selection):
        members = [r for r in rows if r["repositoryId"] + ":" + r["family"] == family]
        counts = Counter(r["status"] for r in members)
        families.append(
            {
                "key": family,
                "rowKeys": [r["key"] for r in members],
                "statusCounts": {s: counts[s] for s in STATUSES},
                "readyRowKeys": [r["key"] for r in members if r["readiness"] == "ready"],
                "blockedRowKeys": [r["key"] for r in members if r["readiness"] == "blocked"],
            }
        )
    return deepcopy(
        {
            "schema": "architecture-source-chart/1",
            "scope": {
                "kind": score_scope,
                "capturedRowCount": captured_count,
                "excludedDependencyGaps": dependency_gaps,
                "repositories": freezes,
                "scoreRowCount": len(rows),
                "evidenceOnlyRowCount": len(evidence_rows),
                "selectedFamilyKeys": sorted(selection),
                "selectedRowKeys": sorted(selected),
                "prerequisiteClosureRowKeys": sorted(closure),
                "fleetComplete": False,
            },
            "activity": {"state": "not_collected"},
            "modelMapping": {"state": "not_qualified"},
            "families": families,
            "rows": {r["key"]: r for r in rows},
            "dependencyCycles": cycle_groups(rows),
            "evidenceRows": evidence_rows,
        }
    )
