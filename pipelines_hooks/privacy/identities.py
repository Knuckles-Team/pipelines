"""Derive the local identities the privacy gate treats as sensitive.

``AGENT_UTILITIES_PRIVACY_IDENTIFIERS`` (comma or newline separated) is a
DECLARED override: when set it replaces the ambient OS/git candidates, so CI
and pre-commit can pin one deterministic identity set regardless of host. It
keeps the fleet-wide variable name so one operator override works everywhere.
"""

from __future__ import annotations

import getpass
import re
import socket
from pathlib import Path
from dataclasses import dataclass

from pipelines_hooks.core.gitenv import run_git
from pipelines_hooks.core.settings import setting

GENERIC_IDENTIFIERS = frozenset(
    {"admin", "agent", "apps", "build", "developer", "home", "localhost", "maintainer",
     "maintainers", "root", "runner", "service", "user", "workspace"}
)


def _identifiers_from_path(value: str) -> set[str]:
    normalized = value.replace("\\", "/")
    return {name for pattern in (r"/home/([^/]+)", r"/Users/([^/]+)") for name in re.findall(pattern, normalized, flags=re.IGNORECASE)}


def _passwd_name() -> str:
    try:
        import pwd
    except ImportError:
        return ""
    import os

    return pwd.getpwuid(os.getuid()).pw_name


def _ambient_candidates(root: Path) -> tuple[set[str], set[str]]:
    hostname = socket.gethostname()
    candidates = {getpass.getuser(), hostname, hostname.split(".", 1)[0], Path.home().name, _passwd_name()}
    candidates.update(setting(name) for name in ("USER", "LOGNAME", "USERNAME"))
    candidates.update(_identifiers_from_path(str(Path.home())))
    common = run_git(root, ("rev-parse", "--path-format=absolute", "--git-common-dir"))
    if common.returncode == 0:
        candidates.update(_identifiers_from_path(common.stdout.strip()))
    candidates.update(_git_values(root, "user.email"))
    names = _git_values(root, "user.name")
    candidates.update(name for name in names if "@" in name)
    return candidates, names


def _git_values(root: Path, key: str) -> set[str]:
    return {line.strip() for line in run_git(root, ("config", "--get", key)).stdout.splitlines()}


def _usable(values: set[str]) -> frozenset[str]:
    return frozenset(v.casefold() for v in values if v and len(v) >= 4 and v.casefold() not in GENERIC_IDENTIFIERS)


@dataclass(frozen=True)
class LocalIdentities:
    """Strict identity sources and Git-display-name-only candidates."""

    strict: frozenset[str]
    display_names: frozenset[str] = frozenset()


def derive_identity_candidates(root: Path) -> LocalIdentities:
    """Keep explicit, account, host, path and email sources strict everywhere."""
    override = setting("AGENT_UTILITIES_PRIVACY_IDENTIFIERS")
    if override:
        return LocalIdentities(_usable({value.strip() for value in re.split(r"[,\n]", override)}))
    candidates, names = _ambient_candidates(root)
    strict = _usable(candidates)
    return LocalIdentities(strict, _usable(names) - strict)
