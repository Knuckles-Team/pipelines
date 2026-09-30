"""Disposable Git fleet builder: six content layouts, no network or sibling repos."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

from scripts.sync_mkdocs_theme import THEME_FILES, sync_theme


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root: Path) -> str:
    git(root, "add", ".")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
    return git(root, "rev-parse", "HEAD")


def repository(root: Path) -> None:
    root.mkdir(parents=True)
    git(root, "init", "-q")


def pin(root: Path, reference: dict) -> Path:
    reference["revision"] = commit(root)
    destination = root.parent / reference["revision"]
    root.rename(destination)
    return destination


def workflow(root: Path, pipeline: dict, content: str) -> None:
    folder = root / ".github/workflows"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pages.yml").write_text(
        f"jobs:\n  pages:\n    uses: {pipeline['repository']}/.github/workflows/pages_pipeline.yml@{pipeline['revision']}\n"
        f"    with:\n      content_source: {content}\n      shared_theme_enabled: true\n"
    )


def fleet_fixture(root: Path) -> dict:
    pipeline = {"repository": "example/pipelines"}
    source = root / pipeline["repository"] / "pending"
    repository(source)
    for item in THEME_FILES:
        path = source / "templates/mkdocs-theme" / item.source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"canonical {item.source}\n".encode())
    source = pin(source, pipeline)
    consumers = []
    for index, content in enumerate(("docs", "pages", "site/source", "manual", "reference", "guide")):
        item = {"repository": f"example/consumer-{index}", "content_source": content, "shared_theme_enabled": True}
        target = root / item["repository"] / "pending"
        repository(target)
        sync_theme(source_root=source, repository_root=target, content_source=content, mode="sync")
        (target / "mkdocs.yml").write_text(f"docs_dir: {content}\n")
        workflow(target, pipeline, content)
        pin(target, item)
        consumers.append(item)
    return {"schema_version": 1, "pipeline": pipeline, "consumers": consumers}


def consumer_root(root: Path, declaration: dict, index: int = 0) -> Path:
    item = declaration["consumers"][index]
    return root / item["repository"] / item["revision"]


def revise(root: Path, declaration: dict, mutate, index: int = 0) -> dict:
    updated = copy.deepcopy(declaration)
    target = consumer_root(root, updated, index)
    mutate(target)
    pin(target, updated["consumers"][index])
    return updated


def declaration_file(root: Path, value: dict) -> Path:
    repository(root)
    path = root / "fleet.json"
    path.write_text(json.dumps(value))
    commit(root)
    return path
