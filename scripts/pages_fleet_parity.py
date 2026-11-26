"""Offline exact-ref Pages asset comparison; no publication or live gates."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.pages_fleet_declaration import ParityError, canonical, digest, validate
from scripts.pages_fleet_trees import UNVERIFIED_ERRORS, ExactTree, resolve
from scripts.pages_fleet_workflow import validate_workflow
from scripts.readiness.errors import ReadinessTckError
from scripts.sync_mkdocs_theme import THEME_FILES


def reason(exc: Exception) -> str:
    if isinstance(exc, (ParityError, ReadinessTckError)):
        return str(exc)
    return "source-unavailable"


def compare_asset(source: ExactTree, target: ExactTree, *, item, content: str) -> dict:
    path = f"{content}/{item.destination}" if item.content_relative else item.destination
    result = {
        "path": path,
        "source": f"templates/mkdocs-theme/{item.source}",
        "expected_sha256": None,
        "actual_sha256": None,
        "status": "unverified",
        "reason": None,
    }
    try:
        result["expected_sha256"] = digest(source.read(result["source"]))
        result["actual_sha256"] = digest(target.read(path))
    except UNVERIFIED_ERRORS as exc:
        result["reason"] = reason(exc)
        return result
    result["status"] = "pass" if result["expected_sha256"] == result["actual_sha256"] else "mismatch"
    if result["status"] == "mismatch":
        result["reason"] = "digest-mismatch"
    return result


#: Ownership a consumer site must state (PIPE-PAGES-R008): the process and the front door each name their owner.
OWNERSHIP = {
    "process": re.compile(r"\bprocess\b[^\n.]*\bowned by\b[^\n.]*\bpipelines\b", re.I),
    "front-door": re.compile(r"\bfront door\b[^\n.]*\bowned by\b[^\n.]*(?:organization|\.github)", re.I),
}
QUICK_START = re.compile(r"^#{1,6}\s+quick\s*start\b[^\n]*\n(?P<body>.*?)(?=^#{1,6}\s|\Z)", re.I | re.M | re.S)
STDIO_BLOCK = re.compile(r"```[^\n]*\n[^`]*\bstdio\b[^`]*```", re.I)


def check_content(target: ExactTree, content: str) -> dict:
    """The consumer's index page states process and front-door ownership and shows a stdio quick start."""
    path = f"{content}/index.md"
    result = {"path": path, "ownership": {}, "quick_start": None, "status": "unverified", "reason": None}
    try:
        text = target.read(path).decode("utf-8")
    except UNVERIFIED_ERRORS as exc:
        result["reason"] = reason(exc)
        return result
    except UnicodeError:
        result["reason"] = "content-not-utf-8"
        return result
    result["ownership"] = {name: bool(pattern.search(text)) for name, pattern in OWNERSHIP.items()}
    section = QUICK_START.search(text)
    result["quick_start"] = bool(section and STDIO_BLOCK.search(section.group("body")))
    ok = all(result["ownership"].values()) and result["quick_start"]
    result["status"] = "pass" if ok else "mismatch"
    result["reason"] = None if ok else "ownership-or-quick-start-missing"
    return result


def verdict(results: list[dict]) -> str:
    statuses = {item["status"] for item in results}
    if "unverified" in statuses:
        return "unverified"
    if "mismatch" in statuses:
        return "mismatch"
    return "pass"


def check_consumer(root: Path, consumer: dict, *, source: ExactTree, pipeline: dict) -> dict:
    result = consumer_record(consumer)
    try:
        populate_consumer(result, root, consumer, source=source, pipeline=pipeline)
    except UNVERIFIED_ERRORS as exc:
        result["reason"] = reason(exc)
    return result


def verify(declaration: dict, fixtures: Path) -> dict:
    """Recompute all exact refs; never reuse an earlier pass or write a consumer."""
    fleet = validate(declaration)
    pipeline = fleet["pipeline"]
    result = {
        "schema_version": 1,
        "provider": "offline-git-fixtures",
        "public_source_verified": False,
        "fleet_sha256": digest(canonical(fleet).encode()),
        "pipeline": dict(pipeline, tree=None),
        "status": "unverified",
        "reason": None,
        "consumers": [consumer_record(item) for item in fleet["consumers"]],
    }
    try:
        populate_fleet(result, fixtures, fleet)
    except UNVERIFIED_ERRORS as exc:
        result["reason"] = reason(exc)
        for item in result["consumers"]:
            item.update(status="unverified", reason=reason(exc))
    return result


def populate_consumer(result: dict, root: Path, consumer: dict, *, source: ExactTree, pipeline: dict) -> None:
    target = resolve(root, consumer)
    result["tree"] = target.tree
    if not consumer["shared_theme_enabled"]:
        raise ParityError("shared-theme-disabled")
    validate_workflow(target, consumer, pipeline)
    result["assets"] = [
        compare_asset(source, target, item=item, content=consumer["content_source"]) for item in THEME_FILES
    ]
    result["content"] = check_content(target, consumer["content_source"])
    target.clean()
    result["status"] = verdict([*result["assets"], result["content"]])


def populate_fleet(result: dict, fixtures: Path, fleet: dict) -> None:
    pipeline = fleet["pipeline"]
    source = resolve(fixtures, pipeline)
    result["pipeline"]["tree"] = source.tree
    result["consumers"] = [
        check_consumer(fixtures, item, source=source, pipeline=pipeline)
        for item in sorted(fleet["consumers"], key=lambda item: item["repository"])
    ]
    source.clean()
    result["status"] = verdict(result["consumers"])


def consumer_record(consumer: dict) -> dict:
    return {
        "repository": consumer["repository"],
        "commit": consumer["revision"],
        "tree": None,
        "commit_url": f"https://github.com/{consumer['repository']}/commit/{consumer['revision']}",
        "content_source": consumer["content_source"],
        "status": "unverified",
        "reason": None,
        "assets": [],
        "content": None,
    }
