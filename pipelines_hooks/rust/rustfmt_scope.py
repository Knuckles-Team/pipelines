"""rustfmt-scope: check-only rustfmt over the Rust files of the current change.

The toolchain is the exact channel pinned in ``rust-toolchain.toml``; the edition
comes from each file's nearest manifest. A formatter or toolchain manifest
change widens the read-only check to every tracked Rust file. The gate never
writes the tree. ``[tool.pipelines_hooks.rustfmt_scope]`` may name
``guard_files`` (paths whose change widens the check) and ``skip_prefixes``
(default ``vendor/``); a file whose first line says ``@generated`` is skipped.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tomllib
from collections import defaultdict
from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, nul_split, repo_root

CONFIGURATION_FILES = frozenset({"Cargo.toml", "rust-toolchain.toml", "rustfmt.toml"})
_CHANNEL = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\Z")
_EDITION = re.compile(r"\d{4}\Z")


def normalise(root: Path, raw: str) -> str:
    """A safe repository-relative path, or a refusal."""
    if not raw or Path(raw).is_absolute():
        raise CannotRun(f"not a repository-relative path: {raw!r}")
    clean = Path(os.path.normpath(raw))
    if clean == Path(".") or ".." in clean.parts or clean.parts[0] == ".git":
        raise CannotRun(f"path leaves the Rust scope: {raw}")
    if (root / clean).is_symlink() or not (root / clean).resolve().is_relative_to(root.resolve()):
        raise CannotRun(f"symlinked path is outside the formatter contract: {raw}")
    return clean.as_posix()


def in_scope(path: str, guards: frozenset[str], skip: tuple[str, ...]) -> bool:
    """A Rust file, a formatter/toolchain manifest, or a declared guard file."""
    if Path(path).suffix == ".rs":
        return not path.startswith(skip)
    return Path(path).name in CONFIGURATION_FILES or path in guards


def pinned_channel(root: Path) -> str:
    """The exact numeric release pinned in ``rust-toolchain.toml``."""
    toolchain = root / "rust-toolchain.toml"
    if not toolchain.is_file():
        raise CannotRun("rust-toolchain.toml is required to pin the rustfmt toolchain")
    try:
        channel = tomllib.loads(toolchain.read_text(encoding="utf-8")).get("toolchain", {}).get("channel")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, AttributeError) as exc:
        raise CannotRun(f"cannot read rust-toolchain.toml: {exc}") from exc
    if not isinstance(channel, str) or not _CHANNEL.fullmatch(channel):
        raise CannotRun("rust-toolchain.toml channel must be an exact numeric release (for example 1.96.0)")
    return channel


def edition_of(root: Path, path: str) -> str:
    """The package (or workspace package) edition of the file's nearest manifest."""
    current = (root / path).parent
    while True:
        manifest = current / "Cargo.toml"
        if manifest.is_file():
            break
        if current == root:
            raise CannotRun(f"no Cargo.toml found for Rust file {path}")
        current = current.parent
    document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    edition = document.get("package", {}).get("edition") or document.get("workspace", {}).get("package", {}).get(
        "edition"
    )
    if not isinstance(edition, str) or not _EDITION.fullmatch(edition):
        raise CannotRun(f"{manifest.relative_to(root)} has no supported numeric package edition")
    return edition


def changed_paths(root: Path, base: str) -> list[str]:
    """Paths changed in ``BASE...HEAD``."""
    out = git_text(root, ["diff", "--name-only", "--diff-filter=ACMRUXB", "-z", f"{base}...HEAD", "--"])
    return [normalise(root, raw) for raw in nul_split(out)]


def run_rustfmt(root: Path, channel: str, paths: list[str]) -> int:
    """Check each edition group with the pinned rustfmt; the first failure wins."""
    by_edition: defaultdict[str, list[str]] = defaultdict(list)
    for path in paths:
        target = root / path
        if not target.is_file():
            continue
        with target.open("rb") as handle:
            if b"@generated" in handle.readline():
                continue
        by_edition[edition_of(root, path)].append(path)
    if not by_edition:
        print("rustfmt-scope: no existing Rust files in scope")
        return 0
    for edition, group in sorted(by_edition.items()):
        print(f"rustfmt-scope: checking {len(group)} Rust file(s) with Rust {channel} (edition {edition}; check-only)")
        try:
            result = subprocess.run(
                ["rustup", "run", channel, "rustfmt", "--edition", edition, "--check", "--", *group],
                cwd=root,
                check=False,
            )
        except OSError as exc:
            raise CannotRun(f"cannot execute the pinned rustfmt via rustup: {exc}") from exc
        if result.returncode:
            return result.returncode
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rustfmt-scope", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", help="derive the scoped paths from BASE...HEAD")
    parser.add_argument("paths", nargs="*", help="repository-relative paths (pre-commit supplies them)")
    arguments = parser.parse_args(argv)
    if arguments.base and arguments.paths:
        parser.error("--base cannot be combined with explicit paths")
    root = repo_root(arguments.root)
    section = load_config(root).section("rustfmt_scope")
    guards = frozenset(string_tuple(section.get("guard_files", []), "rustfmt_scope.guard_files"))
    skip = string_tuple(section.get("skip_prefixes", ["vendor/"]), "rustfmt_scope.skip_prefixes")
    raw = changed_paths(root, arguments.base) if arguments.base else [normalise(root, p) for p in arguments.paths]
    paths = sorted({path for path in raw if in_scope(path, guards, skip)})
    if not paths:
        print("rustfmt-scope: no Rust or formatting-configuration changes")
        return 0
    if any(Path(p).name in CONFIGURATION_FILES or p in guards for p in paths):
        listed = git_text(root, ["ls-files", "-z", "--", "*.rs"], preserve_index=True)
        paths = sorted(p for p in nul_split(listed) if not p.startswith(skip))
    return run_rustfmt(root, pinned_channel(root), paths)
