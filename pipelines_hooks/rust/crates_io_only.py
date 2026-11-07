"""crates-io-only: every Rust dependency resolves from the official registry.

Three things fail: a ``git`` key on any dependency of any workspace manifest, a
``path`` dependency that resolves outside the repository, and a ``git+`` source
in the committed ``Cargo.lock``. The workspace manifests are every tracked
``Cargo.toml``.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths

_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")


def dependency_tables(document: dict) -> list[tuple[str, dict]]:
    """Every dependency table of one parsed manifest, with its label."""
    workspace = document.get("workspace")
    target = document.get("target")
    candidates: list[tuple[str, object]] = [(name, document.get(name)) for name in _TABLES]
    candidates.append(
        ("workspace.dependencies", workspace.get("dependencies") if isinstance(workspace, dict) else None)
    )
    for cfg, table in target.items() if isinstance(target, dict) else ():
        if isinstance(table, dict):
            candidates.extend((f"target.{cfg}.{name}", table.get(name)) for name in _TABLES)
    return [(label, table) for label, table in candidates if isinstance(table, dict)]


def manifest_findings(root: Path, manifest: Path) -> list[str]:
    """One finding per git source or escaping path dependency of ``manifest``."""
    try:
        document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {manifest}: {exc}") from exc
    relative = manifest.relative_to(root)
    findings: list[str] = []
    for label, table in dependency_tables(document):
        for name, spec in table.items():
            if not isinstance(spec, dict):
                continue
            if "git" in spec:
                findings.append(f"{relative} [{label}] '{name}' has a git source ({spec['git']!r})")
            path = spec.get("path")
            if isinstance(path, str) and not (manifest.parent / path).resolve().is_relative_to(root.resolve()):
                findings.append(
                    f"{relative} [{label}] '{name}' has a path dependency ({path!r}) outside the repository"
                )
    return findings


def lockfile_findings(root: Path) -> list[str]:
    """One finding per ``git+`` source in ``Cargo.lock``."""
    lock = root / "Cargo.lock"
    if not lock.is_file():
        return []
    return [
        f"Cargo.lock line {number} resolves from a git+ source ({line.strip()!r})"
        for number, line in enumerate(lock.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip().startswith("source") and "git+" in line
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="crates-io-only", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    manifests = [root / path for path in tracked_paths(root, ("Cargo.toml", "**/Cargo.toml"))]
    findings = [finding for manifest in manifests for finding in manifest_findings(root, manifest)]
    findings += lockfile_findings(root)
    for finding in findings:
        print(f"crates-io-only: {finding}")
    if findings:
        return 1
    print(f"crates-io-only: {len(manifests)} manifest(s) and Cargo.lock resolve from crates.io only")
    return 0
