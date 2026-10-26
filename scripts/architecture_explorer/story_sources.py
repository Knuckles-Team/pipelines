"""Strict raw-source normalization, before permissive legacy Snapshot conversion."""

from __future__ import annotations

import json
import re

from pipelines_hooks.specs import requirements_doc as requirements
from pipelines_hooks.specs.priority import is_functional

from .story_contract import STATUSES


class SourceGap(ValueError):
    """A precise source path/row could not be normalized without guessing."""


def source_ref(repository, commit, path, fragment):
    return {"repository": repository, "commit": commit, "path": path, "fragment": fragment}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceGap("duplicate JSON field: " + key)
        result[key] = value
    return result


def dependency_evidence(body: str, row_id: str) -> tuple[list[str], list[dict], list[str]]:
    """Follow the shared grammar; retain package/prose/self/repeated context.

    Canonical prerequisite lists are conjunctive. Alternative requirement meaning
    and malformed requirement-like tokens need review, not invented AND edges.
    """
    effective, contexts, occurrences = [], [], []
    for pattern, bare in ((requirements._DEPENDS_RE, True), (requirements._NEEDS_RE, False)):
        for match in pattern.finditer(body):
            run = match.group("run")
            tokens = requirements._TICKED_RE.findall(run)
            residue = requirements._TICKED_RE.sub(" ", run)
            if bare:
                tokens += re.findall(rf"(?<![`\w-])({requirements.ID})(?![\w`])", residue)
            resolved = []
            for token in tokens:
                target = requirements._resolve(token, row_id)
                if target is None and "-R" in token.upper():
                    raise SourceGap(f"{row_id}: malformed requirement-like dependency token {token!r}")
                if target is not None:
                    resolved.append(target)
            if bare and re.search(r"[A-Za-z0-9-]+-R[A-Za-z0-9.]+", residue):
                for token in re.findall(r"[A-Za-z0-9-]+-R[A-Za-z0-9.]+", residue):
                    if requirements._resolve(token, row_id) is None:
                        raise SourceGap(f"{row_id}: malformed requirement-like dependency token {token!r}")
            if bool(set(resolved) - {row_id}) and re.search(r"\bor\b", residue, re.I):
                raise SourceGap(f"{row_id}: ambiguous alternative requirement prerequisites")
            kind = "requirement_prerequisites" if resolved else "non_requirement_context"
            contexts.append({"kind": kind, "text": match.group(0), "tokens": list(tokens)})
            for target in resolved:
                occurrences.append(target)
                if target == row_id:
                    contexts.append({"kind": "ignored_self_reference", "text": match.group(0), "tokens": [target]})
                elif target in effective:
                    contexts.append({"kind": "repeated_reference", "text": match.group(0), "tokens": [target]})
                else:
                    effective.append(target)
    return effective, contexts, occurrences


def declared_dependencies(body: str, row_id: str) -> list[str]:
    return dependency_evidence(body, row_id)[0]


def normalize_family(*, repository: dict, commit: str, family: str, markdown: str, status_text: str) -> list[dict]:
    """Compare raw row inventory with generated status; never default absent state."""
    try:
        status = json.loads(status_text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SourceGap("malformed status JSON") from exc
    if (
        not isinstance(status, dict)
        or not isinstance(status.get("requirements"), list)
        or not isinstance(status.get("spec_id"), str)
        or not status["spec_id"].strip()
    ):
        raise SourceGap("status requires explicit spec_id and requirements list")
    if (
        status.get("schema_version") != 2
        or status.get("owner_repo") != repository["fullName"].split("/")[1]
        or status.get("delivery_state") not in STATUSES
    ):
        raise SourceGap("status schema/owner/aggregate state does not match the frozen canonical repository")
    raw = [requirements.ROW_RE.match(line) for line in markdown.splitlines()]
    raw = [match for match in raw if match]
    ids = [match.group(1) for match in raw]
    if any(not re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R[0-9]{3}(?:\.[0-9]+)*", rid) for rid in ids):
        raise SourceGap("current requirement IDs must use the canonical standard form")
    if any(not rid.startswith(status["spec_id"] + "-R") for rid in ids):
        raise SourceGap("requirement IDs disagree with canonical spec ownership")
    if not ids or len(ids) != len(set(ids)):
        raise SourceGap("empty or duplicate requirements row inventory")
    # A candidate requirement line ignored by the shared parser is a source gap.
    for line in markdown.splitlines():
        cells = line.strip().split("|")
        if len(cells) >= 3 and not cells[0]:
            first = cells[1].strip()
            candidate = first.startswith("`") or "-R" in first.upper() or first.startswith(status["spec_id"] + "-")
            if candidate and not requirements.ROW_RE.match(line):
                raise SourceGap("malformed requirement row ID")
    entries = status["requirements"]
    if not all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in entries):
        raise SourceGap("malformed status row")
    status_ids = [row["id"] for row in entries]
    if len(status_ids) != len(set(status_ids)) or set(status_ids) != set(ids):
        raise SourceGap("requirements/status row inventories disagree or contain duplicates")
    if status.get("requirement_ids") != ids:
        raise SourceGap("generated requirement_ids inventory differs from canonical document order")
    by_id = {row["id"]: row for row in entries}
    parsed = {row.id: row for row in requirements.parse_rows(markdown)}
    output = []
    path = f"specs/{family}/requirements.md"
    for match in raw:
        rid, body = match.group(1), match.group(2)
        row = by_id[rid]
        state = row.get("delivery_state")
        if state not in STATUSES or not parsed[rid].title:
            raise SourceGap(f"{rid}: missing/malformed state or title")
        if bool(parsed[rid].retired_reason) != (state == "RETIRED"):
            raise SourceGap(f"{rid}: retirement declaration/status mismatch")
        for field in ("landed_in", "verified_by"):
            if (
                field not in row
                or not isinstance(row[field], list)
                or not all(isinstance(v, str) and v for v in row[field])
            ):
                raise SourceGap(f"{rid}: explicit {field} evidence list required")
        children = row.get("rollup_of")
        if "rollup_of" in row and (
            not isinstance(children, list)
            or not children
            or len(children) != len(set(children))
            or not all(child in by_id and child != rid for child in children)
        ):
            raise SourceGap(f"{rid}: malformed rollup membership")
        provenance = source_ref(repository["fullName"], commit, path, rid)
        dependencies, context, occurrences = dependency_evidence(body, rid)
        if dependencies != list(parsed[rid].depends_on):
            raise SourceGap(f"{rid}: strict/shared dependency grammar disagreement requires review")
        output.append(
            {
                "key": repository["id"] + ":" + rid,
                "id": rid,
                "repositoryId": repository["id"],
                "title": parsed[rid].title,
                "family": family,
                "status": state,
                "functional": is_functional(status["spec_id"]),
                "rollup": "rollup_of" in row,
                "provenance": provenance,
                "declaredDependencies": dependencies,
                "sourceEvidence": {
                    "dependencyContext": context,
                    "declaredDependencyIds": occurrences,
                    "status": source_ref(repository["fullName"], commit, f"specs/{family}/status.json", rid),
                    "landedIn": row["landed_in"],
                    "verifiedBy": row["verified_by"],
                    "rollupOf": children if children is not None else [],
                },
            }
        )
    return output
