"""Load the repository-configured commit identity allowlist (bounded, versioned JSON).

The allowlist is supplied by the consuming repository, not this package: a
repository-local file by default (``<root>/.config/commit-identity-allowlist.json``),
or a fleet-shared path named through ``COMMIT_IDENTITY_ALLOWLIST``
(:mod:`pipelines_hooks.core.settings`), the same way
:mod:`pipelines_hooks.privacy.identity_catalog` resolves its own external
catalog. Its format is ``{"version": "...", "identities": [{"name": ...,
"email": ...}, ...]}``; a malformed or empty file is rejected rather than
silently widening who is accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.bounded_json import read_bounded_json
from pipelines_hooks.core.errors import CannotRun, Unavailable
from pipelines_hooks.core.settings import setting

MAX_ALLOWLIST_BYTES = 64 * 1024
MAX_IDENTITIES = 256
DEFAULT_RELATIVE_PATH = Path(".config") / "commit-identity-allowlist.json"
REMEDY = (
    'create a commit identity allowlist JSON ({"version": "1", "identities": '
    '[{"name": "...", "email": "..."}]}) at .config/commit-identity-allowlist.json, '
    "or set COMMIT_IDENTITY_ALLOWLIST to its path"
)


class IdentityAllowlistError(ValueError):
    """The configured allowlist violates its bounded, versioned contract."""


@dataclass(frozen=True)
class Identity:
    """One permitted author/committer identity."""

    name: str
    email: str


def _validated_identity(raw: object) -> Identity:
    if not isinstance(raw, dict) or set(raw) != {"name", "email"}:
        raise IdentityAllowlistError("each allowlist entry must have exactly 'name' and 'email'")
    name, email = raw["name"], raw["email"]
    if not isinstance(name, str) or not name.strip():
        raise IdentityAllowlistError("allowlist entry name must be a non-empty string")
    if not isinstance(email, str) or not email.strip() or "@" not in email:
        raise IdentityAllowlistError("allowlist entry email must be a non-empty address")
    return Identity(name=name, email=email)


def validated_terms(raw: object) -> tuple[Identity, ...]:
    """The validated identities of a decoded allowlist payload."""
    if not isinstance(raw, dict) or set(raw) != {"version", "identities"}:
        raise IdentityAllowlistError("allowlist must contain version and identities")
    if not isinstance(raw["version"], str) or not raw["version"].strip():
        raise IdentityAllowlistError("allowlist version must be non-empty")
    identities = raw["identities"]
    if not isinstance(identities, list) or not identities:
        raise IdentityAllowlistError("allowlist identities must be a non-empty list")
    if len(identities) > MAX_IDENTITIES:
        raise IdentityAllowlistError("allowlist exceeds the maximum identity count")
    return tuple(_validated_identity(item) for item in identities)


def load_allowlist(path: Path) -> tuple[Identity, ...]:
    """The allowlist's identities; an oversized or malformed file raises."""
    raw = read_bounded_json(
        path, MAX_ALLOWLIST_BYTES, what="allowlist", error=IdentityAllowlistError
    )
    return validated_terms(raw)


def matches(name: str, email: str, identities: tuple[Identity, ...]) -> bool:
    """Whether ``name``/``email`` is an exact match of a configured identity."""
    return any(name == identity.name and email == identity.email for identity in identities)


def configured_path(root: Path, explicit: Path | None) -> Path:
    """Where the allowlist is read from: ``explicit``, else the env setting, else the repo default."""
    if explicit is not None:
        return explicit
    configured = setting("COMMIT_IDENTITY_ALLOWLIST")
    return Path(configured) if configured else root / DEFAULT_RELATIVE_PATH


def resolved_allowlist(root: Path, explicit: Path | None) -> tuple[Identity, ...]:
    """The validated allowlist at the configured path.

    A missing file is :class:`~pipelines_hooks.core.errors.Unavailable` (a
    fail-closed CI exit, a visible local skip naming the remedy); a present but
    malformed file is :class:`~pipelines_hooks.core.errors.CannotRun` (always
    exit 2), since that is a defect in the input, not an absent prerequisite.
    """
    path = configured_path(root, explicit)
    if not path.exists():
        raise Unavailable(f"the commit identity allowlist {path} is not installed", remedy=REMEDY)
    try:
        return load_allowlist(path)
    except (OSError, IdentityAllowlistError) as exc:
        raise CannotRun(f"cannot load the commit identity allowlist ({type(exc).__name__}: {exc})") from exc
