"""security-sanitizer: no unmasked secret in any source file and no root garbage.

Scans every tracked and untracked, non-ignored file (``git ls-files --cached
--others --exclude-standard``); only when git inventory is unavailable does it
walk the filesystem, excluding generated trees but never hidden source
directories. Files are decoded strictly: silently dropping invalid bytes could
splice a credential around them.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import nul_split, run_git
from pipelines_hooks.security.marker import is_exempt
from pipelines_hooks.source_provider import DiskProvider, FileProvider
from pipelines_hooks.security.sanitizer_rules import (
    ALLOWED_TXT_NAMES,
    EXCLUDED_DIRS,
    EXCLUDED_EXTENSIONS,
    MAX_SCAN_BYTES,
    SECRET_PATTERNS,
    TRANSIENT_NOTE_PATTERNS,
    TRANSIENT_PY_PATTERNS,
    is_placeholder,
)


def _walked_files(root: Path) -> list[Path]:
    """Fallback inventory: hidden source directories stay in, generated trees go."""
    files: list[Path] = []
    for directory, subdirectories, names in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in EXCLUDED_DIRS]
        files.extend(Path(directory) / name for name in names)
    return files


def _kept(relative: Path) -> bool:
    if relative.is_absolute() or ".." in relative.parts:
        raise CannotRun("git reported an unsafe source inventory path")
    return not any(part in EXCLUDED_DIRS for part in relative.parts)


def repository_files(root: Path) -> list[Path]:
    """Git inventory minus generated trees, or a walk when git cannot report one."""
    result = run_git(root, ("ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    if result.returncode != 0:
        return _walked_files(root)
    return [root / relative for relative in map(Path, nul_split(result.stdout)) if _kept(relative)]


def naming_violations(relative: Path) -> list[str]:
    """Repository-hygiene findings derived from a path alone."""
    found = []
    if any(p.fullmatch(relative.name) for p in TRANSIENT_NOTE_PATTERNS):
        found.append(f"Transient agent note detected: '{relative}'. Keep scratch notes outside the repository.")
    if relative.parent != Path("."):
        return found
    if relative.suffix == ".txt" and relative.name.lower() not in ALLOWED_TXT_NAMES:
        found.append(
            f"Non-standard root-level text file detected: '{relative.name}'. Only {sorted(ALLOWED_TXT_NAMES)} are allowed."
        )
    if relative.suffix == ".py" and any(p.fullmatch(relative.name) for p in TRANSIENT_PY_PATTERNS):
        found.append(f"Transient/temporary script detected in root: '{relative.name}'. Move it or delete it.")
    return found


def line_secret_labels(line: str) -> list[str]:
    """Credential labels one source line exposes, unless it carries the justified marker."""
    if is_exempt(line):
        return []
    labels: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        matches = pattern.findall(line)
        labels.extend(label for m in matches if not is_placeholder(m[0] if isinstance(m, tuple) else m))
    return labels


def content_violations(blob: bytes, relative: Path) -> list[str]:
    """Findings in one blob's bytes, judged by its declared path alone."""
    if len(blob) > MAX_SCAN_BYTES:
        return [f"Source file exceeds security scan boundary: '{relative}'"]
    try:
        lines = blob.decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        return [f"Source file could not be inspected: '{relative}'"]
    return [
        f"Potential unmasked secret ({label}) detected in {relative}:{number}. If this is a reviewed "
        "synthetic fixture, mark that line '# sanitizer:ignore - <reason>'; do NOT rename or reword to evade the pattern."
        for number, line in enumerate(lines, 1)
        for label in line_secret_labels(line)
    ]


def secret_violations(path: Path, relative: Path) -> list[str]:
    if path.suffix.lower() in EXCLUDED_EXTENSIONS:
        return []
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return [f"Source file exceeds security scan boundary: '{relative}'"]
        return content_violations(path.read_bytes(), relative)
    except (OSError, UnicodeError):
        return [f"Source file could not be inspected: '{relative}'"]


def scan_repository(root: Path) -> list[str]:
    violations = []
    for path in repository_files(root):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        violations.extend(naming_violations(relative))
        violations.extend(secret_violations(path, relative))
    return violations


def scan_provider(provider: FileProvider) -> list[str]:
    """The same findings against a tree source, read by path and blob digest.

    No working copy is required: the gate lists the tree's declared files
    and reads each blob through the provider, which binds the bytes to
    their declared digest.
    """
    violations = []
    for entry in provider.list_files():
        relative = Path(entry.path)
        if relative.suffix.lower() in EXCLUDED_EXTENSIONS:
            continue
        violations.extend(naming_violations(relative))
        violations.extend(content_violations(provider.read(entry.path), relative))
    return violations


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="security-sanitizer", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--tree",
        type=Path,
        default=None,
        help="a tree source directory, read by path and blob digest with no checkout; wins over --root",
    )
    args = parser.parse_args(argv)
    if args.tree is not None:
        violations = scan_provider(DiskProvider(args.tree.resolve()))
    else:
        violations = scan_repository(args.root.resolve())
    if violations:
        print("SECURITY AND GARBAGE VALIDATION FAILED:")
        for index, violation in enumerate(violations, 1):
            print(f"[{index}] {violation}")
        return 1
    print("security-sanitizer: OK: no root garbage and no unmasked secrets")
    return 0
