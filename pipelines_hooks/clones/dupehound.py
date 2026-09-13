"""Select changed source for dupehound 0.1.2 and run it, fail closed."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pipelines_hooks.clones.contract import DUPEHOUND_MIN_TOKENS, DUPEHOUND_THRESHOLD, EXCLUSIONS, is_excluded
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, nul_split, sanitized_env
from pipelines_hooks.core.paths import relative_to_root

#: dupehound 0.1.2's Lang::from_path map; nothing else may make the gate run.
SUPPORTED_SUFFIXES = frozenset(
    ".c .c++ .cc .cjs .cpp .cts .cs .cxx .go .h .hh .h++ .hpp .hxx .java .js .jsx .mjs "
    ".mts .php .py .pyi .rb .rs .swift .ts .tsx".split()
)
_TEST_DIRECTORIES = frozenset({"tests", "test", "__tests__", "testdata", "spec"})
_TEST_SUFFIXES = (
    "_test.go", "_test.py", "_test.rs", "_spec.rb", "_test.rb", "tests.swift", "test.swift",
    "spec.swift", "test.php", "tests.php", "test.java", "tests.java",
)


def is_test_path(path: str) -> bool:
    """Mirror dupehound 0.1.2's test-path classifier (its check skips these)."""
    parts = path.casefold().split("/")
    name = parts[-1]
    return (
        name in {"tests.rs", "test.rs"}
        or name.startswith(("test_", "conftest."))
        or ".test." in name
        or ".spec." in name
        or name.endswith(_TEST_SUFFIXES)
        or any(part in _TEST_DIRECTORIES for part in parts[:-1])
    )


def changed_paths(root: Path, base_ref: str | None) -> list[str]:
    """Commit-range paths with a base, else staged (else worktree + untracked) paths."""
    if base_ref:
        raw = git_text(root, ("diff", "--name-only", "-z", "--diff-filter=ACMR", f"{base_ref}...HEAD"))
        return sorted(set(nul_split(raw)))
    paths = nul_split(git_text(root, ("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"), preserve_index=True))
    if not paths:
        paths = nul_split(git_text(root, ("diff", "--name-only", "-z", "--diff-filter=ACMR", "HEAD")))
        paths += nul_split(git_text(root, ("ls-files", "-z", "--others", "--exclude-standard")))
    return sorted(set(paths))


def selected_paths(root: Path, paths: list[str]) -> list[str]:
    """Supported, non-test, non-excluded production source only."""
    selected = set()
    for path in paths:
        try:
            normalized = relative_to_root(path, root)
        except ValueError as exc:
            raise CannotRun(f"git reported an unsafe changed path: {exc}") from exc
        if Path(normalized).suffix.lower() in SUPPORTED_SUFFIXES and not is_test_path(normalized) and not is_excluded(normalized):
            selected.add(normalized)
    return sorted(selected)


def command(executable: str, root: Path, base_ref: str | None) -> list[str]:
    arguments = [
        executable, "check", "--json", "--threshold", str(DUPEHOUND_THRESHOLD),
        "--min-tokens", str(DUPEHOUND_MIN_TOKENS), "--exclude-tests",
    ]
    for pattern in EXCLUSIONS:
        arguments.extend(("--exclude", pattern))
    if base_ref:
        arguments.extend(("--diff", base_ref))
    return [*arguments, str(root)]


def run(executable: str, root: Path, base_ref: str | None) -> subprocess.CompletedProcess[str]:
    """Without ``--diff`` dupehound compares the staged index against HEAD."""
    try:
        return subprocess.run(
            command(executable, root, base_ref), cwd=str(root),
            env=sanitized_env(preserve_index=base_ref is None),
            capture_output=True, text=True, timeout=900, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"could not execute dupehound: {exc}") from exc
