"""Run ``kiss check`` on one path and materialize the trees it reads."""

from __future__ import annotations

import subprocess
import tarfile
import tomllib
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, has_head, sanitized_env
from pipelines_hooks.core.layout import KISS_CONFIG, located
from pipelines_hooks.kiss.report import parse_report

LANGUAGES = {".py": "python", ".rs": "rust"}
CONFIG = KISS_CONFIG


def check_config(tree: Path) -> Path:
    """The tree's ``.config/kiss.toml``; a missing file or a ``.kissconfig`` fails closed."""
    config = located(tree, CONFIG)
    if not config.is_file() or config.is_symlink():
        raise CannotRun(f"missing hand-authored {CONFIG} (a regular file)")
    if (tree / ".kissconfig").exists() or (tree / ".kissconfig").is_symlink():
        raise CannotRun(".kissconfig is forbidden: bare kiss check self-calibrates and disables rules")
    return config


def orphan_rule_enabled(tree: Path) -> bool:
    """Whether ``[global] orphan_module_enabled`` is on in the tree's config."""
    try:
        document = tomllib.loads(check_config(tree).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {CONFIG}: {exc}") from exc
    return document.get("global", {}).get("orphan_module_enabled") is True


def _validated(output: str, status: int, path: str) -> str:
    if "Unknown config key" in output:
        raise CannotRun(f"kiss rejected a config key while checking {path}: {output[:300]}")
    if status not in (0, 1) or not output.strip():
        raise CannotRun(f"kiss failed on {path} with exit {status}: {output.strip()[:300]}")
    count = len(parse_report(output))
    clean = "NO VIOLATIONS" in output
    if (status == 0) != (count == 0) or (status == 0) != clean:
        raise CannotRun(f"kiss exit status and report disagree for {path}")
    return output


def check(kiss: str, tree: Path, path: str, *, language: str | None = None) -> str:
    """The validated report for ONE path (a file, or a directory with ``language``)."""
    language = language or LANGUAGES.get(Path(path).suffix)
    if language not in LANGUAGES.values():
        raise CannotRun(f"no KISS language for {path}")
    command = [kiss, "check", "--config", str(check_config(tree)), "--lang", language, path]
    try:
        result = subprocess.run(
            command, cwd=str(tree), env=sanitized_env(), capture_output=True, text=True,
            timeout=900, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"could not run kiss on {path}: {exc}") from exc
    return _validated(result.stdout + result.stderr, result.returncode, path)


def materialize_index(root: Path, destination: Path) -> Path:
    """The complete staged index, checked out under ``destination``."""
    destination.mkdir(parents=True)
    git_text(root, ("checkout-index", "--all", f"--prefix={destination}/"), preserve_index=True)
    return destination


def materialize_head(root: Path, destination: Path) -> Path | None:
    """The HEAD tree under ``destination``, or ``None`` before the first commit."""
    if not has_head(root):
        return None
    destination.mkdir(parents=True)
    archive = destination.parent / f"{destination.name}.tar"
    with archive.open("wb") as stream:
        result = subprocess.run(["git", "archive", "HEAD"], cwd=str(root), env=sanitized_env(), stdout=stream, check=False)
    if result.returncode != 0:
        raise CannotRun("git archive HEAD failed")
    with tarfile.open(archive) as bundle:
        bundle.extractall(destination, filter="data")
    return destination


def reject_symlinks(tree: Path, paths: tuple[str, ...]) -> None:
    """A staged symlink under a scanned root could resolve outside the index tree."""
    for prefix in paths:
        base = tree / prefix
        links = [p for p in base.rglob("*") if p.is_symlink()] if base.is_dir() else []
        if links:
            raise CannotRun(f"staged tree contains a symlink under {prefix}: {links[0].relative_to(tree)}")
