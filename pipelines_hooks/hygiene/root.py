"""root-hygiene: every tracked root entry is declared, with a reason, and nothing stale.

An ALLOWLIST, not a denylist: a genuinely new root entry is justified once,
deliberately, in the repository's ``.config/repo-layout.toml``:

* ``[dirs]`` -- every root directory, dot-directories included;
* ``[files]`` -- every non-dot root file;
* ``[dotfiles]`` -- every root dot-file.

Every value is a non-empty reason. A declared entry that is no longer tracked
fails (a stale manifest is the fiction it exists to prevent), and a self-
installing ratchet config (``FORBIDDEN_ANYWHERE``) fails anywhere in the tree.
Reads the tracked set only, never the filesystem.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.layout import REPO_LAYOUT, located
from pipelines_hooks.core.tracked import tracked_paths

MANIFEST = REPO_LAYOUT
TABLES = ("dirs", "files", "dotfiles")
#: Tool-written calibration files: a ratchet the moment they are tracked.
FORBIDDEN_ANYWHERE = frozenset({".kissconfig", ".complexity-baseline.json"})


def load_manifest(root: Path) -> dict[str, dict[str, str]]:
    path = located(root, MANIFEST)
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"{MANIFEST} is missing or invalid: {exc}") from exc
    unknown = sorted(set(document) - set(TABLES))
    if unknown:
        raise CannotRun(f"{MANIFEST} has unknown table(s): {', '.join(unknown)}")
    tables = {name: document.get(name, {}) for name in TABLES}
    for name, table in tables.items():
        if not isinstance(table, dict) or any(not isinstance(v, str) or not v.strip() for v in table.values()):
            raise CannotRun(f"{MANIFEST}: every [{name}] entry needs a non-empty string reason")
    return tables


def _dotted(names: set[str]) -> set[str]:
    return {name for name in names if name.startswith(".")}


def inspect(paths: list[str], manifest: dict[str, dict[str, str]]) -> dict[str, list[str]]:
    """Every class of violation, by name (all empty means clean)."""
    dirs = {p.split("/", 1)[0] for p in paths if "/" in p}
    files = {p for p in paths if "/" not in p}
    dotfiles = _dotted(files)
    declared_files, declared_dots = set(manifest["files"]), set(manifest["dotfiles"])
    return {
        "forbidden": sorted(p for p in paths if Path(p).name in FORBIDDEN_ANYWHERE),
        "undeclared directory": sorted(dirs - set(manifest["dirs"])),
        "undeclared file": sorted(files - dotfiles - declared_files),
        "undeclared dot-file": sorted(dotfiles - declared_dots),
        "misfiled entry ([files] takes non-dot names, [dotfiles] dot names)": sorted(
            _dotted(declared_files) | (declared_dots - _dotted(declared_dots))
        ),
        "stale directory": sorted(set(manifest["dirs"]) - dirs),
        "stale file": sorted((declared_files | declared_dots) - files),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="root-hygiene", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    manifest = load_manifest(root)
    paths = tracked_paths(root)
    violations = {kind: entries for kind, entries in inspect(paths, manifest).items() if entries}
    if not violations:
        counts = ", ".join(f"{len(manifest[name])} {name}" for name in TABLES)
        print(f"root hygiene: clean ({counts} declared)")
        return 0
    print("FAIL: repository-root hygiene violations.")
    for kind, entries in violations.items():
        for entry in entries:
            print(f"  {kind}: {entry}")
    print(
        f"\nDelete scratch/proof output, move workspace content out of the package, or add a one-line "
        f"reason to {MANIFEST}. Remove stale entries. Never track a self-calibrating config."
    )
    return 1
