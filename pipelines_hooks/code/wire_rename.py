"""wire-rename: renaming a serialized name recomputes the files that digest it in the same change.

A *golden file* is a golden-vector, receipt or digest file named by the ``golden`` globs of
``[tool.pipelines_hooks.wire_rename]``. A *rename* is a changed line that differs from its
predecessor in exactly one identifier. The renamed identifier is *serialized* when the golden
files at the base revision contain it. The gate fails when such a rename sits in the change
while a golden file that holds the old name is not part of the same change: that file's digest
no longer covers the renamed name. A rename of a name no golden file holds passes. Without a
``golden`` list the gate covers no files and says so.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterable
from pathlib import Path

from pipelines_hooks.core import baseref
from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_text, git_text, nul_split, repo_root

IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:[.-][A-Za-z0-9_]+)*")
HUNK_RE = re.compile(r"^@@ ")
MIN_NAME = 3


def glob_regex(pattern: str) -> re.Pattern[str]:
    """A path glob: ``*`` stays inside a directory, ``**`` crosses directories."""
    out, index = [], 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(out))


def matches(path: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    return any(pattern.fullmatch(path) for pattern in patterns)


def renamed_identifiers(diff: str) -> list[tuple[str, str, str]]:
    """``(path, old, new)`` for each changed line pair that differs in exactly one identifier.

    ``diff`` is ``git diff -U0`` output. Within a hunk the removed and added lines pair by position;
    a pair renames an identifier when both lines tokenize alike except for one identifier.
    """
    found: list[tuple[str, str, str]] = []
    path = ""
    removed: list[str] = []
    added: list[str] = []

    def close() -> None:
        for old_line, new_line in zip(removed, added, strict=False):
            pair = _single_rename(old_line, new_line)
            if pair and path:
                found.append((path, *pair))
        removed.clear()
        added.clear()

    header = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            close()
            path, header = "", True
        elif header and line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif HUNK_RE.match(line):
            close()
            header = False
        elif header:
            continue
        elif line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    close()
    return sorted(set(found))


def _single_rename(old_line: str, new_line: str) -> tuple[str, str] | None:
    old_tokens, new_tokens = IDENTIFIER_RE.findall(old_line), IDENTIFIER_RE.findall(new_line)
    if len(old_tokens) != len(new_tokens) or IDENTIFIER_RE.sub("", old_line) != IDENTIFIER_RE.sub("", new_line):
        return None
    differing = [(a, b) for a, b in zip(old_tokens, new_tokens, strict=True) if a != b]
    if len(differing) != 1 or len(differing[0][0]) < MIN_NAME:
        return None
    return differing[0]


def stale_golden_files(root: Path, base: str, patterns: list[re.Pattern[str]], diff: str) -> list[str]:
    """One finding per rename whose old name a golden file holds while that file is unchanged."""
    changed = set(nul_split(git_text(root, ("diff", "--name-only", "-z", base, "HEAD"))))
    golden = [
        p for p in nul_split(git_text(root, ("ls-tree", "-r", "-z", "--name-only", base))) if matches(p, patterns)
    ]
    texts = {path: blob_text(root, f"{base}:{path}") or "" for path in golden}
    findings: list[str] = []
    for path, old, new in renamed_identifiers(diff):
        if matches(path, patterns):
            continue
        findings.extend(
            f"{path}: renames {old!r} to {new!r} but {name} still covers {old!r} and is unchanged"
            for name, text in sorted(texts.items())
            if name not in changed and re.search(rf"(?<![\w.-]){re.escape(old)}(?![\w.-])", text)
        )
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wire-rename", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default=None, help="revision the change is measured against")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    globs = load_config(root).section("wire_rename").get("golden", [])
    patterns = [glob_regex(g) for g in string_tuple(globs, "wire_rename.golden")] if globs else []
    if not patterns:
        print("wire-rename: OK: no golden file globs declared, so no file is covered")
        return 0
    base = baseref.upstream_base(root, args.base)
    if base is None:
        raise CannotRun("no base revision: pass --base or fetch origin/main")
    diff = git_text(root, ("diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames", base, "HEAD"))
    findings = stale_golden_files(root, base, patterns, diff)
    for finding in findings:
        print(f"  - {finding}")
    if findings:
        print("wire-rename FAILED: recompute the golden, receipt or digest file in the same commit.")
        return 1
    print(f"wire-rename: OK: no renamed name is covered by an unchanged golden file ({len(patterns)} glob(s))")
    return 0
