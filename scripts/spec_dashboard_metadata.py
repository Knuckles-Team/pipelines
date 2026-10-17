"""Source-declared relationships and implementation links; no state inference."""

import re
from pathlib import Path
from urllib.parse import quote

if __package__:
    from .spec_dashboard_definitions import outside_fences
    from .spec_dashboard_relations import normalized_edges
    from .spec_dashboard_links import LINK, code_role, source_link, targets
else:
    from spec_dashboard_definitions import outside_fences
    from spec_dashboard_relations import normalized_edges
    from spec_dashboard_links import LINK, code_role, source_link, targets

DECLARATION = re.compile(r"^(Depends-on|Depends on|Extends|References|Code|Component):\s*(.*)$", re.I)
KINDS = {"depends-on": "depends on", "depends on": "depends on", "extends": "extends", "references": "references"}


def declarations(text):
    """Only standalone metadata lines declare dependency semantics."""
    text = outside_fences(text)
    for line in text.splitlines():
        match = DECLARATION.fullmatch(line.strip())
        if match:
            yield match[1].lower(), match[2]


def read_metadata(root, item, *, repository, revision, known):
    result = {
        "component": "Unassigned",
        "code_refs": [],
        "relations": [],
        "plan_diagrams": [],
        "unparsed_references": [],
    }
    directory = root / Path(item["source"]).parent
    for name in ("spec.md", "plan.md"):
        document = directory / name
        if document.is_file() and document.resolve().is_relative_to(root.resolve()):
            if name == "plan.md":
                result["plan_diagrams"] = re.findall(
                    r"```mermaid\s*\n(.*?)```", document.read_text(encoding="utf-8"), re.S
                )
            collect_metadata(result, document, root=root, repository=repository, revision=revision, known=known)
    for field in ("code_refs", "relations", "unparsed_references"):
        result[field] = sorted({tuple(sorted(row.items())) for row in result[field]})
        result[field] = [dict(row) for row in result[field]]
    return result


def collect_metadata(result, document, *, root, repository, revision, known):
    text = outside_fences(document.read_text(encoding="utf-8"))
    for kind, value in declarations(text):
        if kind == "component":
            result["component"] = value.strip() or "Unassigned"
            continue
        collect_declaration(
            result, (kind, value), document, root=root, repository=repository, revision=revision, known=known
        )
    collect_references(result, text, document, root=root, repository=repository, revision=revision)


def collect_references(result, text, document, *, root, repository, revision):
    """Source citations may map existing files but never introduce prerequisite edges."""
    candidates = LINK.findall(text) + [(path, path) for path in re.findall(r"`([^`\n]+/[^`\n]+)`", text)]
    for label, target in candidates:
        url, repo, evidence = source_link(root, document, target, repository=repository, revision=revision)
        row = {
            "label": label,
            "url": url,
            "repository": repo or "Unresolved",
            "evidence": evidence,
            "declared_in": document.relative_to(root).as_posix(),
        }
        collect_reference(result, row, target)


def enrich_records(root, snapshot):
    validate_ids(snapshot["records"])
    repository, revision = snapshot["repository"], snapshot["revision"]
    specs = [row for row in snapshot["records"] if row["kind"] == "spec"]
    known = {
        row["id"]: f"https://github.com/{repository}/blob/{revision}/" + quote(row.get("document", row["source"]))
        for row in specs
    }
    add_requirement_owners(known, snapshot["records"])
    for row in specs:
        row.update(read_metadata(root, row, repository=repository, revision=revision, known=known))
    local = {known[row["id"]]: row["id"] for row in specs}
    snapshot["spec_edges"] = normalized_edges(specs, local)


def collect_declaration(result, declaration, document, *, root, repository, revision, known):
    kind, value = declaration
    for label, target in targets(value, kind=kind, result=result, source=document.relative_to(root).as_posix()):
        url, repo, evidence = source_link(root, document, target, repository=repository, revision=revision)
        if target in known:
            url, repo, evidence = known[target], repository, "local spec declaration"
        row = {
            "label": label,
            "url": url,
            "repository": repo or "Unresolved",
            "evidence": evidence,
            "declared_in": document.relative_to(root).as_posix(),
        }
        if kind == "code":
            result["code_refs"].append(row | {"role": code_role(target)})
        else:
            result["relations"].append(row | {"kind": KINDS[kind]})


def collect_reference(result, row, target):
    url, label = row["url"], row["label"]
    if target.split("#")[0].endswith("/spec.md"):
        if not any(edge["url"] == url and edge["label"] == label for edge in result["relations"]):
            result["relations"].append(row | {"kind": "references"})
    elif url and not any(edge["url"] == url for edge in result["code_refs"]):
        result["code_refs"].append(row | {"role": code_role(target)})


def add_requirement_owners(known, records):
    for row in records:
        if row["kind"] == "requirement" and row.get("parent") in known:
            known[row["id"]] = known[row["parent"]]


def validate_ids(records):
    seen = set()
    for row in records:
        if row["id"] in seen:
            raise ValueError("Duplicate spec or requirement ID: " + row["id"])
        seen.add(row["id"])
