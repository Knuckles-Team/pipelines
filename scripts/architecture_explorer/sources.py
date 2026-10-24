"""Read spec rows and file lists from repositories (local git or the public GitHub API)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pipelines_hooks.specs.requirements_doc import parse_rows

from .details import describe, family_docs, row_parts

ROW_RE = re.compile(r"^\|\s*`([A-Za-z0-9][A-Za-z0-9.\-]*)`\s*\|(.*)$")
OWNER = "Knuckles-Team"
# Organization repositories with ``specs/`` that are not runtime parts (the front door hub).
IGNORED = frozenset({".github"})


@dataclass
class Snapshot:
    """One repository at one commit: its file list and spec rows."""

    repo: str
    slug: str
    head: str = ""
    files: set[str] = field(default_factory=set)
    rows: list[dict] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    docs: dict[str, dict[str, str]] = field(default_factory=dict)
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

    def __init__(self, slug: str, token: str | None = None, sha: str = "") -> None:
        self.slug = slug
        self.token = token
        if not sha:
            meta = self._json(f"https://api.github.com/repos/{OWNER}/{slug}")
            branch = meta["default_branch"]
            sha = self._json(f"https://api.github.com/repos/{OWNER}/{slug}/commits/{branch}")["sha"]
        self.sha = sha

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
        markdown = reader.read(f"specs/{family}/requirements.md")
        text = requirement_text(markdown)
        # Read from the row text, not status.json: a repository's status.json carries depends_on only after it regenerates.
        depends = {row.id: list(row.depends_on) for row in parse_rows(markdown)}
        for req in status.get("requirements", []):
            body = text.get(req["id"], "")
            title = (req.get("title") or "").strip()
            rows.append(
                {
                    "id": req["id"],
                    "title": title,
                    "desc": describe(row_parts(body)[0], title),
                    "landed_in": req.get("landed_in") or [],
                    "verified_by": req.get("verified_by") or [],
                    "rollup_of": req.get("rollup_of") or [],
                    "status": req.get("delivery_state", "SPECIFIED"),
                    "repo": repo,
                    "family": family,
                    "text": body,
                    "req": body.split("|")[0],
                    "spec_id": status.get("spec_id", ""),
                    "depends_on": depends.get(req["id"], []),
                    "rollup": "rollup_of" in req,
                }
            )
    return rows


ALIAS_FILE = ".config/spec-aliases.toml"


def read_aliases(reader, files: set[str]) -> dict[str, str]:
    """Retired ID prefix or row ID -> canonical, from a repository's alias file (empty when absent or unreadable)."""
    if ALIAS_FILE not in files:
        return {}
    try:
        doc = tomllib.loads(reader.read(ALIAS_FILE))
    except (tomllib.TOMLDecodeError, OSError, ValueError, urllib.error.URLError):
        return {}
    return {k: v for k, v in doc.items() if isinstance(k, str) and isinstance(v, str)}


def snapshot(entry: dict, mode: str, workspace: Path | None, token: str | None) -> Snapshot:
    """Read one registry entry."""
    snap = Snapshot(repo=entry["name"], slug=entry["slug"])
    try:
        if mode == "local":
            reader = GitReader(workspace / entry["local"])
        else:
            reader = GitHubReader(entry["slug"], token, entry.get("sha", ""))
        snap.head = reader.head()
        snap.files = reader.files()
        snap.rows = rows_for(reader, entry["name"], snap.files)
        snap.docs = {f: family_docs(reader, snap.files, f) for f in {r["family"] for r in snap.rows}}
        snap.aliases = read_aliases(reader, snap.files)
    except (OSError, KeyError, ValueError, urllib.error.URLError) as exc:
        snap.error = f"{type(exc).__name__}: {exc}"
    return snap


DISCOVER_QUERY = (
    """
query($cursor: String) {
  organization(login: "%s") {
    repositories(first: 50, after: $cursor, orderBy: {field: NAME, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name isArchived isPrivate
        defaultBranchRef { target { oid } }
        specs: object(expression: "HEAD:specs") { ... on Tree { entries { name type } } }
      }
    }
  }
}
"""
    % OWNER
)


def _graphql(token: str, cursor: str | None) -> dict:
    body = json.dumps({"query": DISCOVER_QUERY, "variables": {"cursor": cursor}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"Bearer {token}", "User-Agent": "architecture-explorer"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - fixed https host
        out = json.loads(resp.read())
    if out.get("errors"):
        raise ValueError(f"discovery failed: {out['errors'][0].get('message')}")
    return out["data"]["organization"]["repositories"]


def org_repositories(token: str) -> dict[str, str]:
    """Map each public, unarchived organization repository with a ``specs/`` tree to its head SHA."""
    found: dict[str, str] = {}
    cursor = None
    while True:
        page = _graphql(token, cursor)
        for repo in page["nodes"]:
            ref = repo.get("defaultBranchRef") or {}
            if repo["isArchived"] or repo["isPrivate"] or not repo.get("specs") or not ref:
                continue
            if "entries" in repo["specs"]:
                found[repo["name"]] = ref["target"]["oid"]
        if not page["pageInfo"]["hasNextPage"]:
            return found
        cursor = page["pageInfo"]["endCursor"]


def reconcile(registry: list[dict], found: dict[str, str]) -> list[dict]:
    """Return the scan set: registered repositories that still exist plus every newly discovered one.

    A registered repository that is gone, archived or private, or that no longer has
    ``specs/``, drops out so its rows disappear; a new organization repository with
    ``specs/`` joins as a connector so its rows appear without a registry edit.
    """
    out = [{**e, "sha": found[e["slug"]]} for e in registry if e["slug"] in found]
    known = {e["slug"] for e in registry}
    for slug in sorted(set(found) - known - IGNORED):
        out.append(
            {
                "name": slug,
                "slug": slug,
                "local": f"agent-packages/agents/{slug}",
                "kind": "connector",
                "sha": found[slug],
                "discovered": True,
            }
        )
    return out


def scan_set(registry: list[dict], mode: str, token: str | None) -> list[dict]:
    """Discover the repositories to scan; github mode asks the organization, local mode uses the registry."""
    if mode != "github" or not token:
        return registry
    return reconcile(registry, org_repositories(token))


def load_all(registry: list[dict], mode: str, workspace: Path | None = None, workers: int = 12) -> list[Snapshot]:
    """Read every registry entry in parallel, keeping registry order."""
    token = os.environ.get("GITHUB_TOKEN") or None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda e: snapshot(e, mode, workspace, token), registry))
