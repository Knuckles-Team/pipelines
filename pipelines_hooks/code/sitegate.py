"""The census + diff-scoped engine shared by the swallowed-errors and event-loop gates.

NOT A RATCHET. Instead of a frozen baseline:

* an unconditional CENSUS prints the real totals (sites, per-shape histogram,
  worst files) on every run, pass or fail -- nothing is written to disk;
* enforcement is DIFF-SCOPED, recomputed live from the HEAD blob and keyed by
  CONTENT (never an enclosing symbol, never a line number), so extraction,
  renaming and line motion are invisible and only a genuinely ADDED site fails;
* ``hard_zero`` shapes are enforced absolutely, repository-wide.

Moving an existing site to a different file reads as added in the destination.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.config import load_config
from pipelines_hooks.core.gitenv import blob_text, git_text, has_head, repo_root
from pipelines_hooks.core.tracked import skipped, tracked_or_walked, tracked_paths


@dataclass(frozen=True)
class Site:
    path: str
    line: int
    shape: str
    key: str


@dataclass(frozen=True)
class SiteGate:
    name: str
    scan_source: Callable[[str, str], list[Site]]
    hard_zero: frozenset[str]
    include: Callable[[str], bool]
    remedy: str


def package_sites(gate: SiteGate, root: Path, packages: tuple[str, ...]) -> list[Site]:
    """Every current site under the packages (the census population)."""
    sites: list[Site] = []
    for package in packages:
        for path in tracked_or_walked(root / package, ("*.py",), root=root):
            rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
            if path.is_file() and not skipped(Path(rel)) and gate.include(rel):
                sites.extend(gate.scan_source(rel, path.read_text(encoding="utf-8", errors="replace")))
    return sites


def print_census(gate: SiteGate, sites: list[Site]) -> None:
    files = Counter(site.path for site in sites)
    print(f"{gate.name} census: {len(sites)} site(s) in {len(files)} file(s)")
    for shape, count in Counter(site.shape for site in sites).most_common():
        print(f"  {count:5d}  {shape}")
    for rel, count in files.most_common(5):
        print(f"  top: {count:3d}  {rel}")


def changed_python(root: Path, packages: tuple[str, ...]) -> list[str]:
    """Package ``.py`` paths differing from HEAD (staged or worktree); every file before a first commit."""
    if not has_head(root):
        return sorted(p for p in tracked_paths(root, packages) if p.endswith(".py"))
    paths: set[str] = set()
    for args in (("diff", "--cached", "--name-only", "--diff-filter=ACMR", "HEAD"), ("diff", "--name-only", "--diff-filter=ACMR", "HEAD")):
        paths.update(git_text(root, (*args, "--", *packages), preserve_index=True).splitlines())
    return sorted(p for p in paths if p.endswith(".py"))


def added_sites(gate: SiteGate, root: Path, packages: tuple[str, ...]) -> list[tuple[str, str, int]]:
    """``(path, key, added count)`` for content this change ADDS."""
    added = []
    for rel in changed_python(root, packages):
        if not gate.include(rel) or not (root / rel).is_file():
            continue
        before = Counter(site.key for site in gate.scan_source(rel, blob_text(root, f"HEAD:{rel}") or ""))
        after = Counter(site.key for site in gate.scan_source(rel, (root / rel).read_text(encoding="utf-8", errors="replace")))
        added.extend((rel, key, count - before[key]) for key, count in after.items() if count > before[key])
    return added


def _report(gate: SiteGate, *, forbidden: list[Site], added: list[tuple[str, str, int]]) -> int:
    for site in forbidden:
        print(f"  FORBIDDEN {site.path}:{site.line} [{site.shape}]")
    for rel, key, count in added:
        print(f"  ADDED {rel}: {key}" + (f" (x{count})" if count > 1 else ""))
    if forbidden or added:
        print(gate.remedy)
        return 1
    print(f"{gate.name}: OK: no site added by this change")
    return 0


def report_every_site(gate: SiteGate, target: Path) -> int:
    """Absolute mode over an arbitrary directory: every site, no diff scoping."""
    sites = [
        site
        for path in sorted(target.rglob("*.py"))
        for site in gate.scan_source(path.relative_to(target).as_posix(), path.read_text(encoding="utf-8"))
    ]
    for site in sites:
        print(f"  {site.path}:{site.line} [{site.shape}] {site.key}")
    return 1 if sites else 0


def run(gate: SiteGate, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=gate.name)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("path", nargs="?", help="report EVERY site under this path (no diff scoping)")
    args = parser.parse_args(argv)
    if args.path:
        return report_every_site(gate, Path(args.path).resolve())
    root = repo_root(args.root)
    packages = load_config(root).required_packages()
    sites = package_sites(gate, root, packages)
    print_census(gate, sites)
    forbidden = [site for site in sites if site.shape in gate.hard_zero]
    return _report(gate, forbidden=forbidden, added=added_sites(gate, root, packages))
