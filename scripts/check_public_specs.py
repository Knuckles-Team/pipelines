"""Validate pipeline-owned public specs without network or live environments."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

FILES = ("spec.md", "plan.md", "test-spec.md", "tasks.md", "status.json")
DELIVERY = {"UNKNOWN", "SPECIFIED", "BUILDING", "BUILT", "LANDED", "CLOSED", "DEFERRED", "REJECTED"}
ACCEPTANCE = {"NOT_AUDITED", "PENDING", "ACCEPTED", "FAILED"}
PRIVATE = re.compile(r"plans/|gitlab|homelab|(?:file://|/(?:home|Users|tmp|workspace)/)|\.arpa\b", re.I)
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


def document_errors(root: Path, path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    errors = []
    if len(content.strip()) < 120:
        errors.append(f"{path}: incomplete document")
    if PRIVATE.search(content):
        errors.append(f"{path}: private or local reference")
    for target in LINK.findall(content):
        url = urlsplit(target)
        if url.scheme:
            if url.scheme != "https" or url.hostname is None:
                errors.append(f"{path}: non-public URL")
            continue
        if target.startswith("#"):
            continue
        local = (path.parent / unquote(url.path)).resolve()
        if not local.is_relative_to(root.resolve()) or not local.exists():
            errors.append(f"{path}: broken local link {target}")
    return errors


def status_errors(path: Path) -> tuple[list[str], list[str], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{path}: invalid JSON ({exc})"], [], ""
    if not isinstance(data, dict):
        return [f"{path}: status must be an object"], [], ""
    errors = []
    ids = data.get("requirement_ids")
    if data.get("schema_version") != 1 or not re.fullmatch(r"PIPE-[A-Z0-9-]+", str(data.get("spec_id", ""))):
        errors.append(f"{path}: schema version or spec ID mismatch")
    if data.get("owner_repo") != "pipelines":
        errors.append(f"{path}: wrong owner")
    if not isinstance(ids, list) or not ids or not all(isinstance(item, str) and item for item in ids):
        errors.append(f"{path}: requirement IDs required")
        ids = []
    if data.get("delivery_state") not in DELIVERY or data.get("acceptance_state") not in ACCEPTANCE:
        errors.append(f"{path}: invalid state")
    evidence = data.get("evidence")
    if not isinstance(evidence, list):
        errors.append(f"{path}: evidence must be an array")
        evidence = []
    valid = []
    for item in evidence:
        if not isinstance(item, dict):
            errors.append(f"{path}: evidence item must be an object")
            continue
        commit = item.get("commit", "")
        url = item.get("url", "")
        if (
            not isinstance(commit, str)
            or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or not isinstance(url, str)
            or not url.startswith("https://github.com/")
            or item.get("result") not in {"passed", "failed"}
            or not item.get("description")
        ):
            errors.append(f"{path}: invalid public evidence receipt")
            continue
        valid.append(item)
    merged = next(
        (
            item["commit"] for item in valid
            if item.get("kind") == "merged_head"
            and item.get("result") == "passed"
            and item["url"] == f"https://github.com/Knuckles-Team/pipelines/commit/{item['commit']}"
        ),
        None,
    )
    if data.get("delivery_state") in {"LANDED", "CLOSED"} and not merged:
        errors.append(f"{path}: merged-head evidence required")
    if data.get("acceptance_state") == "ACCEPTED":
        kinds = {
            item.get("kind") for item in valid
            if item.get("commit") == merged and item.get("result") == "passed"
        }
        if not merged or "test" not in kinds or not kinds & {"consumer", "release"}:
            errors.append(f"{path}: acceptance receipts required")
    return errors, ids, data.get("spec_id", "")


def problems(root: Path) -> list[str]:
    specs = root / "specs"
    errors = []
    template = specs / "_template"
    for filename in FILES:
        if not (template / filename).is_file():
            errors.append(f"{template / filename}: missing template file")
    index = (specs / "README.md").read_text(encoding="utf-8")
    used: set[str] = set()
    spec_ids: set[str] = set()
    for feature in sorted(path for path in specs.iterdir() if path.is_dir() and path.name != "_template"):
        for filename in FILES:
            path = feature / filename
            if not path.is_file():
                errors.append(f"{path}: missing owner contract")
            elif filename != "status.json":
                errors.extend(document_errors(root, path))
        if f"]({feature.name}/spec.md)" not in index:
            errors.append(f"{feature}: absent from index")
        status = feature / "status.json"
        if status.is_file():
            issues, ids, spec_id = status_errors(status)
            errors.extend(issues)
            if spec_id in spec_ids:
                errors.append(f"{status}: duplicate spec ID {spec_id}")
            spec_ids.add(spec_id)
            for item in ids:
                if item in used:
                    errors.append(f"{status}: duplicate requirement owner {item}")
                used.add(item)
    errors.extend(document_errors(root, specs / "README.md"))
    return errors


def main() -> int:
    errors = problems(Path(__file__).resolve().parents[1])
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Public pipeline specs are structurally complete and self-contained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
