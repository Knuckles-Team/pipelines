"""Whether the current CI run is a pull request from a fork: external contributions are exempt.

Outside contributors are welcome and are not subject to the commit-identity
allowlist. In GitHub Actions a pull request from a fork is the one case where
the committer of record is never one of the fleet's own sanctioned identities,
so :mod:`pipelines_hooks.identity.range_gate` exempts it rather than checking
it. Detection reads ``GITHUB_EVENT_NAME``/``GITHUB_EVENT_PATH`` through
:mod:`pipelines_hooks.core.settings` (never ``os.environ`` directly) and
compares the event payload's ``pull_request.head.repo.full_name`` against
``pull_request.base.repo.full_name``. Anything else -- a push, a same-repository
pull request, a local run, or a missing/unreadable event payload -- is treated
as NOT exempt, fail-closed.
"""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.core.bounded_json import read_bounded_json
from pipelines_hooks.core.settings import setting

MAX_EVENT_BYTES = 2 * 1024 * 1024


class _EventPayloadError(ValueError):
    """The GitHub Actions event payload could not be read or parsed."""


def _repo_full_names(payload: object) -> tuple[str, str] | None:
    """``(head, base)`` full repository names of a ``pull_request`` payload, or ``None``."""
    if not isinstance(payload, dict):
        return None
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        return None
    try:
        head = pull_request["head"]["repo"]["full_name"]
        base = pull_request["base"]["repo"]["full_name"]
    except (KeyError, TypeError):
        return None
    return (head, base) if isinstance(head, str) and isinstance(base, str) else None


def is_fork_pull_request() -> bool:
    """Whether this run checks a pull request whose head repository is a fork of the base."""
    if setting("GITHUB_EVENT_NAME") != "pull_request":
        return False
    event_path = setting("GITHUB_EVENT_PATH")
    if not event_path:
        return False
    try:
        payload = read_bounded_json(
            Path(event_path), MAX_EVENT_BYTES, what="GitHub event payload", error=_EventPayloadError
        )
    except (OSError, _EventPayloadError):
        return False
    names = _repo_full_names(payload)
    return names is not None and names[0] != names[1]
