"""Canonical source normalization shared by current and historical snapshots."""

import json
import re

if __package__:
    from .spec_dashboard_definitions import enrich_definitions
else:
    from spec_dashboard_definitions import enrich_definitions

STATES = {"SPECIFIED": "specified", "LANDED": "landed", "VERIFIED": "verified", "RETIRED": "retired"}
# RETIRED is an internal generator value for a delivered row whose code was removed.
# It is filtered out before display; any other unknown value renders as INVALID.


def record(raw, path, kind, *, parent=None):
    """Allowlist public fields; status never propagates between specs and slices."""
    delivery = str(raw.get("delivery_state", "MISSING")).upper()
    return {
        "id": str(raw.get("spec_id", raw.get("id", path.parent.name))),
        "kind": kind,
        "parent": parent,
        "source": path.as_posix(),
        "title": str(raw.get("title", raw.get("spec_id", raw.get("id", path.parent.name)))),
        "delivery_state": delivery if delivery in STATES else "INVALID",
        "state": STATES.get(delivery, "invalid"),
        "done": delivery == "VERIFIED",
        **public_evidence(raw),
    }


def read_records(root, config):
    records = []
    seen = set()
    for source in config["sources"]:
        for path in sorted(root.glob(source["glob"])):
            relative = path.relative_to(root)
            if "_template" in relative.parts or path.resolve().is_relative_to(root) is False:
                continue
            if relative in seen:
                continue
            seen.add(relative)
            records.extend(read_source(path, relative, source.get("kind", "spec"), root=root))
    return [item for item in records if item["delivery_state"] != "RETIRED"]


def read_source(path, relative, kind, *, root):
    if kind not in {"spec", "requirement"}:
        raise ValueError("kind must be spec or requirement")
    raw = json.loads(path.read_text(encoding="utf-8"))
    result = source_records(raw, relative, kind)
    if kind == "spec":
        result[0].update(document_metadata(path, root))
        enrich_definitions(result, path, root)
    return result


def source_records(raw, relative, kind):
    primary = record(raw, relative, kind)
    result = [primary]
    children = {str(item["id"]): item for item in raw.get("requirements", [])}
    ids = dict.fromkeys([*raw.get("requirement_ids", []), *children])
    for identifier in ids:
        result.append(
            record(children.get(identifier, {"id": identifier}), relative, "requirement", parent=primary["id"])
        )
    return result


def document_metadata(path, root):
    document = path.with_name("spec.md")
    if not document.is_file() or not document.resolve().is_relative_to(root):
        return {}
    headings = re.findall(r"^# (.+)$", document.read_text(encoding="utf-8"), re.MULTILINE)
    metadata = {"document": document.relative_to(root).as_posix()}
    if headings:
        metadata["title"] = headings[0]
    return metadata


def public_list(raw, field):
    value = raw.get(field, [])
    return value if isinstance(value, list) else []


def public_evidence(raw):
    return {
        "landed_in": [
            sha
            for sha in public_list(raw, "landed_in")
            if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{7,40}", sha)
        ],
        "verified_by": [test for test in public_list(raw, "verified_by") if isinstance(test, str)],
    }
