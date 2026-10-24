"""Rule pl.x: root files the canonical scaffold does not have are deleted when nothing references them.

The canonical scaffold (universal-skills ``scaffold_connector.py``) has none of ``SCAFFOLD_EXTRAS``. A file is deleted only
when no tracked file (or file a rule just wrote) mentions it by name; every referenced file stays and gets a non-blocking
review item naming the referencing files, so the owner decides. Deletions are re-evaluated until none is left to make,
because deleting one file (``MANIFEST.in``) can leave another (``mcp_config.json``) unreferenced.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import tomllib
from pathlib import Path

from pipelines_hooks.hygiene.connector_central.base import Ctx, rule

ORDER: tuple[str, ...] = ("pl.x",)

#: Top-level entries the canonical scaffold does not have; ``MANIFEST.in`` first so its globs stop counting once it is gone.
SCAFFOLD_EXTRAS = (
    "MANIFEST.in",
    "requirements.txt",
    ".dockerignore",
    ".env.example",
    "mcp_config.json",
    "opencode.json",
)
#: Files whose mentions are history or resolved pins, never a use of the candidate.
IGNORED_REFERRERS = frozenset({"uv.lock", "CHANGELOG.md"})
SKIP_DIRS = frozenset({".git", ".venv", "node_modules", "__pycache__", "site-packages", ".mypy_cache", ".ruff_cache"})
MAX_BYTES = 2_000_000
MAX_NAMED = 8


def _is_dockerfile(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".Dockerfile")


def _repo_files(ctx: Ctx) -> list[str]:
    """Tracked files plus files a rule wrote, minus deleted ones; a directory that is not a git checkout is walked."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        r = subprocess.run(["git", "ls-files", "-z", "--", "."], cwd=ctx.root, capture_output=True, text=True, env=env)
        listed = [p for p in r.stdout.split("\0") if p] if r.returncode == 0 else []
    except OSError:
        listed = []
    if not listed:
        listed = [
            p.relative_to(ctx.root).as_posix()
            for p in ctx.root.rglob("*")
            if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(ctx.root).parts)
        ]
    names = {*listed, *ctx.changed} - ctx.deleted
    return sorted(n for n in names if (ctx.root / n).is_file())


def _mention(name: str) -> re.Pattern[str]:
    """``name`` as a whole word or path component (not inside ``dev-requirements.txt`` or ``requirements.txt.bak``)."""
    return re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(name)}(?![A-Za-z0-9_-]|\.[A-Za-z0-9])")


def _text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_BYTES:
            return ""
        raw = path.read_bytes()
    except OSError:
        return ""
    return "" if b"\0" in raw else raw.decode("utf-8", errors="replace")


def _glob_references(ctx: Ctx, name: str) -> list[str]:
    """Files whose packaging globs include ``name``: ``[tool.setuptools.package-data]`` and ``MANIFEST.in``."""
    found: list[str] = []
    try:
        data = tomllib.loads(ctx.read("pyproject.toml"))
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    listed = data.get("tool", {}).get("setuptools", {}).get("package-data", {})
    for globs in listed.values() if isinstance(listed, dict) else []:
        if any(isinstance(g, str) and "/" not in g and fnmatch.fnmatch(name, g) for g in globs):
            found.append("pyproject.toml")
            break
    if ctx.exists("MANIFEST.in") and name != "MANIFEST.in":
        for line in ctx.read("MANIFEST.in").splitlines():
            words = line.split("#", 1)[0].split()
            if len(words) > 1 and words[0] in {"include", "global-include", "recursive-include", "graft"}:
                if any(fnmatch.fnmatch(name, w) for w in words[1:]):
                    found.append("MANIFEST.in")
                    break
    return found


def referrers(ctx: Ctx, name: str, files: list[str]) -> list[str]:
    """Every file that still uses ``name``, sorted and without duplicates."""
    pattern = _mention(name)
    found = set(_glob_references(ctx, name)) if name == "mcp_config.json" else set()
    for rel in files:
        if rel == name or rel in IGNORED_REFERRERS or rel.rsplit("/", 1)[-1] in IGNORED_REFERRERS:
            continue
        if name == ".dockerignore" and _is_dockerfile(rel):
            found.add(rel)  # a Dockerfile that still exists is built with this ignore file
        elif pattern.search(_text(ctx.root / rel)):
            found.add(rel)
    return sorted(found)


@rule("pl.x")
def rule_x(ctx: Ctx) -> None:
    pending = [n for n in SCAFFOLD_EXTRAS if ctx.exists(n)]
    kept: dict[str, list[str]] = {}
    progress = True
    while pending and progress:
        progress = False
        files = _repo_files(ctx)
        for name in list(pending):
            who = referrers(ctx, name, files)
            if who:
                kept[name] = who
                continue
            kept.pop(name, None)
            ctx.delete(name, "pl.x")
            pending.remove(name)
            progress = True
            files = _repo_files(ctx)
    for name in pending:
        who = kept.get(name, [])
        shown = ", ".join(who[:MAX_NAMED]) + (f" and {len(who) - MAX_NAMED} more" if len(who) > MAX_NAMED else "")
        ctx.note("pl.x", f"{name} is not in the canonical scaffold but is referenced by: {shown}", name, False)
