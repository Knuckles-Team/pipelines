"""sprawl: versioned clones, merge/conflict artifacts, botched-merge markers, tracked binaries.

A botched merge leaves the marker as a line of its own, so it is matched at the
start of a line; Markdown code spans and fences are stripped first, so a
document quoting the marker is not a finding. There is no file allowlist.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import skipped, tracked_or_walked

CLONE_RE = re.compile(r".*_(v\d+|old|new)\.py$")
ARTIFACT_SUFFIXES = (".orig", ".rej", ".bak")
MERGE_MARKER_RE = re.compile(r"^[ \t]*# --- Merged from", re.MULTILINE)
MAX_BINARY_BYTES = 1_000_000
_MD_FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_MD_INLINE_RE = re.compile(r"`[^`\n]*`")
TEXT_SUFFIXES = frozenset(
    ".py .rs .ts .tsx .js .jsx .md .txt .toml .yaml .yml .json .ttl .cfg .ini .sh .html .css .lock".split()
)
EXTRA_SKIPS = frozenset({"target", ".hypothesis", ".ruff_cache", ".mypy_cache", ".pytest_cache"})


def _content_violations(path: Path, relative: Path) -> list[str]:
    if path.suffix not in TEXT_SUFFIXES:
        size = path.stat().st_size
        return [f"tracked binary > {MAX_BINARY_BYTES} bytes: {relative} ({size} bytes)"] if size > MAX_BINARY_BYTES else []
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".md":
        text = _MD_INLINE_RE.sub("", _MD_FENCE_RE.sub("", text))
    return [f"botched-merge marker in: {relative}"] if MERGE_MARKER_RE.search(text) else []


def scan(root: Path) -> list[str]:
    violations = []
    for path in tracked_or_walked(root, (), root=root):
        relative = path.relative_to(root)
        if skipped(relative) or any(part in EXTRA_SKIPS for part in relative.parts) or not path.is_file():
            continue
        if CLONE_RE.match(path.name):
            violations.append(f"versioned-clone file: {relative}")
        if path.name.endswith(ARTIFACT_SUFFIXES):
            violations.append(f"merge/conflict artifact: {relative}")
        violations.extend(_content_violations(path, relative))
    return violations


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sprawl", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    violations = scan(repo_root(parser.parse_args(argv).root))
    if violations:
        print("Anti-sprawl gate FAILED:")
        for violation in sorted(violations):
            print(f"  - {violation}")
        return 1
    print("sprawl: OK: no sprawl or hygiene violations")
    return 0
