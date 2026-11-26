"""spec-artifacts: admit an externally emitted ``spec-bundle/1`` of one capability's spec files.

A bundle is the six standard files of one existing capability directory plus a manifest that binds the
encoding, the schema version, the canonical row IDs, each file's relative path and its sha256. The gate
reads the Git index bytes, never rewrites them, and refuses what it cannot prove: an unknown format
version, a path that leaves the capability directory, a missing or altered file, a second directory for
an already-owned capability. Graph ingestion is owned by the engine adapter; its receipt is optional
evidence, and an unavailable consumer is unchecked evidence plus exit status 2 when one is required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, git_text, nul_split, repo_root
from pipelines_hooks.specs.ids import ROW_RE
from pipelines_hooks.specs.requirements_doc import parse_rows

FORMAT = "spec-bundle/1"
MANIFEST = "spec-bundle.json"
STANDARD_FILES = ("spec.md", "plan.md", "requirements.md", "tasks.md", "test-spec.md", "checklists/requirements.md")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _prefix(row_id: str) -> str:
    return row_id.rsplit("-R", 1)[0]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="spec-artifacts", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--manifest", help=f"repo-relative manifest; default every specs/*/{MANIFEST}")
    parser.add_argument("--feature", help="spec ID prefix a new feature targets; it must extend that owner")
    parser.add_argument("--consumer-receipt", type=Path, help="JSON receipt of the owner ingestion adapter")
    parser.add_argument("--require-consumer", action="store_true", help="exit 2 when no consumer receipt is given")
    return parser.parse_args(argv)


def _manifests(root: Path, requested: str | None) -> list[str]:
    if requested:
        return [requested]
    tracked = nul_split(git_text(root, ("ls-files", "-z", "--", f"specs/*/{MANIFEST}")))
    return sorted(tracked)


def _load(root: Path, path: str) -> dict | None:
    data = blob_bytes(root, f":{path}")
    if data is None:
        return None
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def _owners(root: Path) -> dict[str, list[str]]:
    """Spec ID prefix -> the specs/ directories whose requirements.md define rows under it."""
    owners: dict[str, list[str]] = {}
    for path in nul_split(git_text(root, ("ls-files", "-z", "--", "specs/*/requirements.md"))):
        data = blob_bytes(root, f":{path}") or b""
        directory = PurePosixPath(path).parts[1]
        for prefix in {_prefix(row.id) for row in parse_rows(data.decode("utf-8", "replace"))}:
            owners.setdefault(prefix, []).append(directory)
    return owners


def _file_findings(root: Path, manifest: dict, capability: str) -> tuple[list[str], dict[str, bytes]]:
    findings: list[str] = []
    data: dict[str, bytes] = {}
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return ["files: the manifest lists no files"], data
    seen: set[str] = set()
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str):
            findings.append(f"files: an entry has no path: {entry!r}")
            continue
        parts = PurePosixPath(path).parts
        if PurePosixPath(path).is_absolute() or ".." in parts or parts[:2] != ("specs", capability):
            findings.append(f"{path}: path escapes the capability directory specs/{capability}/")
            continue
        seen.add("/".join(parts[2:]))
        blob = blob_bytes(root, f":{path}")
        if blob is None:
            findings.append(f"{path}: missing file")
            continue
        if _sha(blob) != entry.get("sha256"):
            findings.append(f"{path}: altered input bytes (sha256 differs from the manifest)")
        try:
            blob.decode("utf-8")
        except UnicodeError:
            findings.append(f"{path}: not UTF-8")
        data[path] = blob
    findings += [
        f"specs/{capability}/{name}: the bundle lacks this standard file" for name in STANDARD_FILES if name not in seen
    ]
    return findings, data


def _ownership_findings(root: Path, manifest: dict, capability: str, feature: str | None) -> list[str]:
    spec_id = manifest.get("spec_id")
    owners = _owners(root)
    findings = []
    if not isinstance(spec_id, str) or spec_id not in owners:
        findings.append(f"spec_id: {spec_id!r} owns no rows under specs/")
    elif sorted(set(owners[spec_id])) != [capability]:
        findings.append(
            f"ownership: {spec_id} is owned by {sorted(set(owners[spec_id]))}; the bundle names specs/{capability}/"
        )
    if feature and feature in owners and set(owners[feature]) != {capability}:
        findings.append(
            f"feature {feature} must extend specs/{sorted(set(owners[feature]))[0]}/, not specs/{capability}/"
        )
    return findings


def _id_findings(manifest: dict, data: dict[str, bytes], capability: str) -> list[str]:
    text = data.get(f"specs/{capability}/requirements.md", b"").decode("utf-8", "replace")
    found = sorted(row.id for row in parse_rows(text))
    declared = manifest.get("ids")
    if not isinstance(declared, list) or not all(isinstance(i, str) and ROW_RE.match(f"| {i} |") for i in declared):
        return ["ids: the manifest lacks a list of canonical row IDs"]
    if sorted(declared) != found:
        return [
            f"ids: manifest IDs differ from requirements.md (missing {sorted(set(found) - set(declared))[:3]}, extra {sorted(set(declared) - set(found))[:3]})"
        ]
    return []


def _consumer(receipt: Path | None, consumed: dict[str, str]) -> tuple[dict, list[str]]:
    if receipt is None:
        return {"status": "unchecked", "reason": "owner ingestion adapter receipt not provided"}, []
    try:
        document = json.loads(receipt.read_text(encoding="utf-8"))
        digests, revision = document["digests"], document["revision"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CannotRun(f"consumer receipt {receipt} is unreadable: {exc}") from exc
    drift = [
        f"consumer: {p} was read as {digests.get(p)!r}, not the bundle digest"
        for p, d in sorted(consumed.items())
        if digests.get(p) != d
    ]
    return {"status": "checked", "revision": revision, "consumer": document.get("consumer")}, drift


def check_bundle(root: Path, path: str, arguments: argparse.Namespace) -> tuple[list[str], dict]:
    """Findings and the evidence record of one manifest."""
    manifest = _load(root, path)
    if manifest is None:
        return [f"{path}: the manifest is missing or not a UTF-8 JSON object"], {}
    if manifest.get("format") != FORMAT:
        return [f"{path}: unknown format version {manifest.get('format')!r}; only {FORMAT} is supported"], {}
    capability = PurePosixPath(path).parts[1]
    findings = [] if manifest.get("encoding") == "utf-8" else [f"{path}: encoding must be utf-8"]
    if manifest.get("capability") != capability:
        findings.append(f"{path}: capability {manifest.get('capability')!r} is not its directory {capability!r}")
    file_findings, data = _file_findings(root, manifest, capability)
    findings += file_findings + _ownership_findings(root, manifest, capability, arguments.feature)
    findings += _id_findings(manifest, data, capability)
    consumed = {name: _sha(blob) for name, blob in sorted(data.items())}
    consumer, drift = _consumer(arguments.consumer_receipt, consumed)
    evidence = {
        "gate": "spec-artifacts",
        "format": FORMAT,
        "input_digest": _sha(blob_bytes(root, f":{path}") or b""),
        "consumed": consumed,
        "owner": {"spec_id": manifest.get("spec_id"), "directory": capability, "repository": root.name},
        "canonical_generation": {"status": "checked", "revision": git_text(root, ("rev-parse", "HEAD")).strip()},
        "graph_ingestion": consumer,
    }
    return findings + drift, evidence


def main(argv: list[str]) -> int:
    arguments = _parse_args(argv)
    root = repo_root(arguments.root)
    manifests = _manifests(root, arguments.manifest)
    if not manifests:
        print("spec-artifacts: no spec-bundle manifest to check")
        return 0
    status, unchecked = 0, False
    for path in manifests:
        findings, evidence = check_bundle(root, path, arguments)
        if evidence:
            print(json.dumps(evidence, sort_keys=True))
            unchecked = unchecked or evidence["graph_ingestion"]["status"] == "unchecked"
        for line in findings:
            print(f"spec-artifacts: {line}")
        status = 1 if findings else status
    if arguments.require_consumer and unchecked and not status:
        raise CannotRun("the owner ingestion adapter is unavailable; the bundle's graph ingestion is unchecked")
    return status
