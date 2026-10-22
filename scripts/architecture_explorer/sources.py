"""Read spec rows and file lists from repositories (local git or the public GitHub API)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

ROW_RE = re.compile(r"^\|\s*`([A-Za-z0-9][A-Za-z0-9.\-]*)`\s*\|(.*)$")
OWNER = "Knuckles-Team"


@dataclass
class Snapshot:
    """One repository at one commit: its file list and spec rows."""

    repo: str
    slug: str
    head: str = ""
    files: set[str] = field(default_factory=set)
    rows: list[dict] = field(default_factory=list)
    error: str = ""


class GitReader:
    """Read a local clone at its remote default branch (read only)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.ref = self._ref()

    def _git(self, *args: str) -> str:
        env = {"GIT_TERMINAL_PROMPT": "0", "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        proc = subprocess.run(
            ["git", "-C", str(self.path), *args], capture_output=True, text=True, env=env, check=False
        )
        return proc.stdout

    def _ref(self) -> str:
        head = self._git("symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD").strip()
        return head or "origin/main"

    def head(self) -> str:
        return self._git("rev-parse", "--short=10", self.ref).strip()

    def files(self) -> set[str]:
        return {f for f in self._git("ls-tree", "-r", "--name-only", self.ref).split("\n") if f}

    def read(self, path: str) -> str:
        return self._git("show", f"{self.ref}:{path}")


class GitHubReader:
    """Read a public repository over the GitHub REST API and raw content URLs."""

    def __init__(self, slug: str, token: str | None = None) -> None:
        self.slug = slug
        self.token = token
        meta = self._json(f"https://api.github.com/repos/{OWNER}/{slug}")
        branch = meta["default_branch"]
        commit = self._json(f"https://api.github.com/repos/{OWNER}/{slug}/commits/{branch}")
        self.sha = commit["sha"]

    def _get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "architecture-explorer"})
        if self.token and url.startswith("https://api.github.com/"):
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https hosts
            return resp.read()

    def _json(self, url: str) -> dict:
        return json.loads(self._get(url))

    def head(self) -> str:
        return self.sha[:10]

    def files(self) -> set[str]:
        tree = self._json(f"https://api.github.com/repos/{OWNER}/{self.slug}/git/trees/{self.sha}?recursive=1")
        return {e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"}

    def read(self, path: str) -> str:
        try:
            return self._get(f"https://raw.githubusercontent.com/{OWNER}/{self.slug}/{self.sha}/{path}").decode()
        except urllib.error.HTTPError:
            return ""


def spec_dirs(files: set[str]) -> list[str]:
    """Return the spec family directories that hold a status.json."""
    return sorted(
        f.split("/")[1]
        for f in files
        if f.startswith("specs/")
        and f.endswith("/status.json")
        and f.count("/") == 2
        and not f.split("/")[1].startswith("_")
    )


def requirement_text(markdown: str) -> dict[str, str]:
    """Map each requirement ID in a requirements.md table to its row text."""
    out: dict[str, str] = {}
    for line in markdown.splitlines():
        match = ROW_RE.match(line)
        if match:
            out[match.group(1)] = match.group(2)
    return out


def rows_for(reader, repo: str, files: set[str]) -> list[dict]:
    """Read every spec row of one repository."""
    rows = []
    for family in spec_dirs(files):
        try:
            status = json.loads(reader.read(f"specs/{family}/status.json") or "{}")
        except json.JSONDecodeError:
            continue
        text = requirement_text(reader.read(f"specs/{family}/requirements.md"))
        for req in status.get("requirements", []):
            body = text.get(req["id"], "")
            rows.append(
                {
                    "id": req["id"],
                    "title": (req.get("title") or "").strip(),
                    "status": req.get("delivery_state", "SPECIFIED"),
                    "repo": repo,
                    "family": family,
                    "text": body,
                    "req": body.split("|")[0],
                }
            )
    return rows


def snapshot(entry: dict, mode: str, workspace: Path | None, token: str | None) -> Snapshot:
    """Read one registry entry."""
    snap = Snapshot(repo=entry["name"], slug=entry["slug"])
    try:
        if mode == "local":
            reader = GitReader(workspace / entry["local"])
        else:
            reader = GitHubReader(entry["slug"], token)
        snap.head = reader.head()
        snap.files = reader.files()
        snap.rows = rows_for(reader, entry["name"], snap.files)
    except (OSError, KeyError, ValueError, urllib.error.URLError) as exc:
        snap.error = f"{type(exc).__name__}: {exc}"
    return snap


def load_all(registry: list[dict], mode: str, workspace: Path | None = None, workers: int = 12) -> list[Snapshot]:
    """Read every registry entry in parallel, keeping registry order."""
    token = os.environ.get("GITHUB_TOKEN") or None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda e: snapshot(e, mode, workspace, token), registry))
