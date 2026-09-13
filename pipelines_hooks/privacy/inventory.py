"""Which files each privacy pass reads.

A tracked test fixture or workflow in a PUBLIC repository discloses exactly as
much as tracked source, so neither pass is scoped by a borrowed directory
allowlist: selection is by suffix over git's tracked/non-ignored inventory,
and a gitignored tree never reaches the gate.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import nul_split, run_git

TEXT_SUFFIXES = frozenset({".md", ".json", ".yaml", ".yml", ".toml"})
SOURCE_SUFFIXES = frozenset({".js", ".md", ".ps1", ".py", ".rs", ".sh", ".ts", ".yaml", ".yml"})
PUBLIC_TEXT_TREES = frozenset({"docs", ".github", "tests", ".specify", "examples"})
_EXCLUDED_DIRECTORIES = frozenset(
    {".acp-sessions", ".benchmarks", ".git", ".hypothesis", ".mypy_cache", ".nox", ".pytest_cache",
     ".pytest_tmp", ".ruff_cache", ".tox", ".venv", "__pycache__", "build", "dist", "htmlcov",
     "node_modules", "site", "target", "venv", "workspace"}
)
MAX_SCAN_FILES = 500_000


def is_public_artifact(relative: Path) -> bool:
    if relative.suffix.casefold() not in TEXT_SUFFIXES or "skills" in relative.parts:
        return False
    return relative.parts[0] in PUBLIC_TEXT_TREES or len(relative.parts) == 1 or relative.suffix.casefold() == ".toml"


def _walk(root: Path) -> list[Path]:
    """A bounded no-git snapshot inventory that never follows links."""
    files: list[Path] = []
    for directory, names, file_names in os.walk(root, topdown=True):
        current = Path(directory)
        names[:] = sorted(
            n for n in names
            if n not in _EXCLUDED_DIRECTORIES and not n.endswith(".egg-info") and stat.S_ISDIR((current / n).lstat().st_mode)
        )
        files.extend(current / n for n in sorted(file_names) if stat.S_ISREG((current / n).lstat().st_mode))
        if len(files) > MAX_SCAN_FILES:
            raise CannotRun("privacy source inventory exceeds its file bound")
    return files


def candidates(root: Path) -> list[Path]:
    """Tracked plus untracked non-ignored files, or a walk for a no-git snapshot."""
    if not (root / ".git").exists():
        return _walk(root)
    result = run_git(root, ("ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    if result.returncode != 0:
        return _walk(root)
    return [root / name for name in nul_split(result.stdout)]


def is_bundled_connector_profile(relative: Path) -> bool:
    parts = tuple(part.casefold() for part in relative.parts)
    return parts[:4] == ("agent_utilities", "protocols", "source_connectors", "profiles") and relative.suffix.casefold() in {
        ".py", ".json", ".yaml", ".yml",
    }
