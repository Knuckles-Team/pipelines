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


def _load_status(path: Path) -> tuple[dict | None, str]:
    """Parse ``status.json`` into an object, or return the reason it cannot be used."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{path}: invalid JSON ({exc})"
    if not isinstance(data, dict):
        return None, f"{path}: status must be an object"
    return data, ""


def _identity_errors(path: Path, data: dict) -> list[str]:
    errors = []
    if data.get("schema_version") != 1 or not re.fullmatch(r"PIPE-[A-Z0-9-]+", str(data.get("spec_id", ""))):
        errors.append(f"{path}: schema version or spec ID mismatch")
    if data.get("owner_repo") != "pipelines":
        errors.append(f"{path}: wrong owner")
    return errors


def _requirement_ids(data: dict) -> list[str] | None:
    """The declared requirement IDs, or ``None`` when they are missing or malformed."""
    ids = data.get("requirement_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(item, str) and item for item in ids):
        return None
    return ids


def _state_errors(path: Path, data: dict) -> list[str]:
    if data.get("delivery_state") not in DELIVERY or data.get("acceptance_state") not in ACCEPTANCE:
        return [f"{path}: invalid state"]
    return []


def _is_public_receipt(item: dict) -> bool:
    commit = item.get("commit", "")
    url = item.get("url", "")
    return (
        isinstance(commit, str)
        and re.fullmatch(r"[0-9a-f]{40}", commit) is not None
        and isinstance(url, str)
        and url.startswith("https://github.com/")
        and item.get("result") in {"passed", "failed"}
        and bool(item.get("description"))
    )


def _valid_evidence(path: Path, data: dict, errors: list[str]) -> list[dict]:
    """Well-formed public evidence receipts; malformed entries are reported into ``errors``."""
    evidence = data.get("evidence")
    if not isinstance(evidence, list):
        errors.append(f"{path}: evidence must be an array")
        return []
    valid = []
    for item in evidence:
        if not isinstance(item, dict):
            errors.append(f"{path}: evidence item must be an object")
        elif not _is_public_receipt(item):
            errors.append(f"{path}: invalid public evidence receipt")
        else:
            valid.append(item)
    return valid


def _merged_head(valid: list[dict]) -> str | None:
    return next(
        (
            item["commit"] for item in valid
            if item.get("kind") == "merged_head"
            and item.get("result") == "passed"
            and item["url"] == f"https://github.com/Knuckles-Team/pipelines/commit/{item['commit']}"
        ),
        None,
    )


def _receipt_errors(path: Path, data: dict, valid: list[dict]) -> list[str]:
    errors = []
    merged = _merged_head(valid)
    if data.get("delivery_state") in {"LANDED", "CLOSED"} and not merged:
        errors.append(f"{path}: merged-head evidence required")
    if data.get("acceptance_state") == "ACCEPTED":
        kinds = {
            item.get("kind") for item in valid
            if item.get("commit") == merged and item.get("result") == "passed"
        }
        if not merged or "test" not in kinds or not kinds & {"consumer", "release"}:
            errors.append(f"{path}: acceptance receipts required")
    return errors


def status_errors(path: Path) -> tuple[list[str], list[str], str]:
    data, failure = _load_status(path)
    if data is None:
        return [failure], [], ""
    errors = _identity_errors(path, data)
    ids = _requirement_ids(data)
    if ids is None:
        errors.append(f"{path}: requirement IDs required")
        ids = []
    errors.extend(_state_errors(path, data))
    valid = _valid_evidence(path, data, errors)
    errors.extend(_receipt_errors(path, data, valid))
    return errors, ids, data.get("spec_id", "")


def _template_errors(specs: Path) -> list[str]:
    template = specs / "_template"
    return [f"{template / filename}: missing template file" for filename in FILES if not (template / filename).is_file()]


def _feature_file_errors(root: Path, feature: Path, index: str) -> list[str]:
    errors = []
    for filename in FILES:
        path = feature / filename
        if not path.is_file():
            errors.append(f"{path}: missing owner contract")
        elif filename != "status.json":
            errors.extend(document_errors(root, path))
    if f"]({feature.name}/spec.md)" not in index:
        errors.append(f"{feature}: absent from index")
    return errors


def _ownership_errors(status: Path, used: set[str], spec_ids: set[str]) -> list[str]:
    """Status errors plus spec-ID and requirement-owner uniqueness across features."""
    errors, ids, spec_id = status_errors(status)
    if spec_id in spec_ids:
        errors.append(f"{status}: duplicate spec ID {spec_id}")
    spec_ids.add(spec_id)
    for item in ids:
        if item in used:
            errors.append(f"{status}: duplicate requirement owner {item}")
        used.add(item)
    return errors


def problems(root: Path) -> list[str]:
    specs = root / "specs"
    errors = _template_errors(specs)
    index = (specs / "README.md").read_text(encoding="utf-8")
    used: set[str] = set()
    spec_ids: set[str] = set()
    for feature in sorted(path for path in specs.iterdir() if path.is_dir() and path.name != "_template"):
        errors.extend(_feature_file_errors(root, feature, index))
        status = feature / "status.json"
        if status.is_file():
            errors.extend(_ownership_errors(status, used, spec_ids))
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
