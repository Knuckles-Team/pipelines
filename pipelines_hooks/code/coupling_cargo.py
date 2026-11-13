"""Cargo crate layers for the coupling gate (PIPE-GATES-R088.2).

A Cargo workspace opts in with ``[[tool.pipelines_hooks.coupling.cargo_layers]]``,
most stable first, each entry ``{name, units}`` where units are package names.
Normal and build dependencies (plain and per target) are layered; dev
dependencies are not, because a test may reach upward. Renamed dependencies
(``package = "..."``, also through ``[workspace.dependencies]``) resolve to
their package.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

from pipelines_hooks.code.coupling import Layer, _cycle_groups
from pipelines_hooks.core.errors import CannotRun

_TABLES = ("dependencies", "build-dependencies")


def _read(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {path.name}: {exc}") from exc


def _members(root: Path, manifest: dict) -> dict[str, Path]:
    """Package name -> member manifest path, for every workspace member."""
    workspace = manifest.get("workspace")
    if not isinstance(workspace, dict):
        raise CannotRun("coupling.cargo_layers needs a Cargo.toml with a [workspace] table at the repository root")
    excluded = {(root / item).resolve() for item in workspace.get("exclude", [])}
    members: dict[str, Path] = {}
    for pattern in workspace.get("members", []):
        for directory in sorted(root.glob(pattern)):
            path = directory / "Cargo.toml"
            if directory.resolve() in excluded or not path.is_file():
                continue
            package = _read(path).get("package", {})
            if not isinstance(package, dict) or not isinstance(package.get("name"), str):
                raise CannotRun(f"{path.relative_to(root)} has no package name")
            members[package["name"]] = path
    if isinstance(manifest.get("package"), dict) and isinstance(manifest["package"].get("name"), str):
        members[manifest["package"]["name"]] = root / "Cargo.toml"
    return members


def _dependency_tables(manifest: dict) -> Iterator[dict]:
    for table in _TABLES:
        yield manifest.get(table, {})
    for target in manifest.get("target", {}).values():
        if isinstance(target, dict):
            for table in _TABLES:
                yield target.get(table, {})


def _package(key: str, spec: object, shared: dict) -> str:
    if isinstance(spec, dict):
        if spec.get("workspace") is True:
            return _package(key, shared.get(key, {}), {})
        if isinstance(spec.get("package"), str):
            return spec["package"]
    return key


def _line(text: str, key: str) -> int:
    match = re.search(rf"^[ \t]*{re.escape(key)}[ \t]*(?:=|\.)", text, re.MULTILINE)
    return text.count("\n", 0, match.start()) + 1 if match else 1


def cargo_layer_findings(root: Path, layers: tuple[Layer, ...]) -> list[str]:
    """Upward, unlayered and cyclic crate dependencies of the workspace at ``root``."""
    manifest_path = root / "Cargo.toml"
    if not manifest_path.is_file():
        raise CannotRun("coupling.cargo_layers needs a Cargo.toml at the repository root")
    manifest = _read(manifest_path)
    members = _members(root, manifest)
    shared = manifest.get("workspace", {}).get("dependencies", {})
    rank = {unit: number for number, layer in enumerate(layers) for unit in layer.units}
    findings: list[str] = []
    edges: dict[str, set[str]] = {name: set() for name in members}
    edge_site: dict[tuple[str, str], str] = {}
    for name, path in sorted(members.items()):
        relative = path.relative_to(root).as_posix()
        if name not in rank:
            findings.append(f"{relative}:1: COUPLING-UNLAYERED-CRATE {name} is named in no cargo_layers entry")
        text = path.read_text(encoding="utf-8")
        for table in _dependency_tables(_read(path)):
            for key, spec in table.items():
                target = _package(key, spec, shared)
                if target not in members or target == name:
                    continue
                site = f"{relative}:{_line(text, key)}"
                edges[name].add(target)
                edge_site.setdefault((name, target), site)
                if name in rank and target in rank and rank[target] > rank[name]:
                    findings.append(
                        f"{site}: COUPLING-UPWARD-CRATE {name} ({layers[rank[name]].name}) depends on "
                        f"{target} ({layers[rank[target]].name}), a less stable layer"
                    )
    for group in _cycle_groups(edges):
        inside = sorted(site for (a, b), site in edge_site.items() if a in group and b in group)
        findings.append(f"{inside[0]}: COUPLING-CRATE-CYCLE among crates {', '.join(group)}")
    return sorted(set(findings))
