"""The connector repository set: ``workspace.yml`` (the ``agents`` group) intersected with the non-archived GitHub repos.

Local checkout directories are never the source: stale clones of retired repositories stay on disk. An archived
repository, or one the workspace manifest does not list, is not a connector for any driver, census or report.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import yaml

from pipelines_hooks.core.settings import setting

#: The operator's workspace root: never a literal machine path in source (PIPE-GATES-R016.118).
WORKSPACE_ROOT = Path(setting("PIPELINES_WORKSPACE_ROOT") or Path.home() / "workspace").expanduser()
DEFAULT_WORKSPACE = WORKSPACE_ROOT / "workspace.yml"
ORG = "Knuckles-Team"
GROUP = ("agent-packages", "agents")
_URL_NAME = re.compile(r"github\.com[/:][^/]+/([^/]+?)(?:\.git)?$")


def workspace_connectors(workspace: Path = DEFAULT_WORKSPACE) -> list[str]:
    """Repository names of the ``agent-packages/agents`` group in the workspace manifest, in manifest order."""
    node = yaml.safe_load(workspace.read_text(encoding="utf-8"))
    for key in GROUP:
        node = (node.get("subdirectories") or {}).get(key)
        if node is None:
            raise ValueError(f"{workspace} has no {'/'.join(GROUP)} group")
    names = []
    for repo in node.get("repositories") or []:
        m = _URL_NAME.search(str(repo.get("url", "")))
        if m:
            names.append(m.group(1))
    return names


def active_github_repos(org: str = ORG) -> set[str]:
    """Names of the org's repositories that are not archived (``gh repo list --no-archived``)."""
    r = subprocess.run(
        ["gh", "repo", "list", org, "--no-archived", "--limit", "1000", "--json", "name"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {row["name"] for row in json.loads(r.stdout)}


def connector_repos(
    workspace: Path = DEFAULT_WORKSPACE, active: Callable[[], set[str]] = active_github_repos
) -> list[str]:
    """Workspace connectors that are active on GitHub."""
    live = active()
    return [name for name in workspace_connectors(workspace) if name in live]


def only_active(
    names: list[str], workspace: Path = DEFAULT_WORKSPACE, active: Callable[[], set[str]] = active_github_repos
) -> list[str]:
    """``names`` filtered to the connector set (an explicit list may not name an archived or unlisted repository)."""
    allowed = set(connector_repos(workspace, active))
    return [n for n in names if n in allowed]
