"""spec-id-index: write the cross-repo spec row ID index that plan-conformance resolves foreign IDs against.

The index is JSON ``{"repos": {"<repo>": ["<row ID>", ...]}}``: every row ID that a
``specs/*/requirements.md`` of each organization repository defines on its default branch. It is read
from the GitHub API (``GITHUB_TOKEN`` raises the rate limit) and is the same data the architecture
explorer reads. Refresh it by re-running ``pipelines-hook spec-id-index --out <path>``; CI does this
before the spec gates whenever a plan changes.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.settings import setting
from pipelines_hooks.specs.ids import ROW_RE

OWNER = "Knuckles-Team"
API = "https://api.github.com"
REQUIREMENTS = "specs/{}/requirements.md"


def _get(url: str, token: str, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "spec-id-index", "Accept": accept})  # noqa: S310 - fixed https host
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read()


def _repos(token: str) -> dict[str, str]:
    """Non-archived organization repositories -> default branch."""
    found: dict[str, str] = {}
    page = 1
    while True:
        batch = json.loads(_get(f"{API}/orgs/{OWNER}/repos?per_page=100&page={page}", token))
        found.update(
            {r["name"]: r["default_branch"] for r in batch if not r.get("archived") and r["name"] != ".github"}
        )
        if len(batch) < 100:
            return found
        page += 1


def _read(name: str, branch: str, path: str, token: str) -> str:
    """A file's text: raw content first (no API quota), the contents API for a repository raw cannot see."""
    try:
        return _get(f"https://raw.githubusercontent.com/{OWNER}/{name}/{branch}/{path}", "").decode(errors="replace")
    except urllib.error.HTTPError:
        raw = _get(f"{API}/repos/{OWNER}/{name}/contents/{path}?ref={branch}", token, "application/vnd.github.raw")
        return raw.decode(errors="replace")


def _repo_ids(name: str, branch: str, token: str) -> list[str]:
    try:
        tree = json.loads(_get(f"{API}/repos/{OWNER}/{name}/git/trees/{branch}?recursive=1", token))
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 409):  # an empty repository or one the token cannot read holds no readable specs
            return []
        raise
    paths = [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob" and e["path"].startswith("specs/")]
    ids: set[str] = set()
    for path in paths:
        parts = path.split("/")
        if len(parts) == 3 and parts[2] == "requirements.md" and not parts[1].startswith("_"):
            text = _read(name, branch, path, token)
            ids.update(m.group(1) for m in map(ROW_RE.match, text.splitlines()) if m)
    return sorted(ids)


def build_index(token: str) -> dict[str, list[str]]:
    """Every repository's row IDs; repositories without specs are left out."""
    try:
        repos = _repos(token)
        out = {name: _repo_ids(name, branch, token) for name, branch in sorted(repos.items())}
    except (OSError, ValueError, KeyError) as exc:
        raise CannotRun(f"cannot read the organization's specs from GitHub: {exc}") from exc
    return {name: ids for name, ids in out.items() if ids}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spec-id-index", description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    index = build_index(setting("GITHUB_TOKEN"))
    args.out.write_text(json.dumps({"repos": index}, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print(f"spec-id-index: wrote {sum(map(len, index.values()))} IDs of {len(index)} repositories to {args.out}")
    return 0
