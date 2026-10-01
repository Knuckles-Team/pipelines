"""Load the configured commit identity allowlist (bounded, versioned JSON).

Resolution order: an explicit ``--allowlist`` path, else the fleet-shared path
named through ``COMMIT_IDENTITY_ALLOWLIST`` (:mod:`pipelines_hooks.core.settings`),
else a repository-local file if one is tracked
(``<root>/.config/commit-identity-allowlist.json``), else the fleet default
packaged inside this package (``fleet-default-allowlist.json``, shipped via
``[tool.setuptools.package-data]`` in ``pyproject.toml``) -- the same precedence
:mod:`pipelines_hooks.privacy.identity_catalog` uses for its own external
catalog, one step deeper. Because the packaged default always ships with the
package, a missing allowlist is no longer possible; only a malformed file (at
whichever path was resolved) still raises. Its format is ``{"version": "...",
"identities": [{"name": ..., "email": ...}, ...]}``; a malformed or empty file
is rejected rather than silently widening who is accepted.
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
#: The fleet default shipped inside this package; always present once installed.
FLEET_DEFAULT_PATH = Path(__file__).resolve().parent / "fleet-default-allowlist.json"
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
    """Where the allowlist is read from.

    ``explicit``, else the env setting, else a repository-local file if one is
    present, else the fleet default packaged with this package.
    """
    if explicit is not None:
        return explicit
    configured = setting("COMMIT_IDENTITY_ALLOWLIST")
    if configured:
        return Path(configured)
    repository_local = root / DEFAULT_RELATIVE_PATH
    return repository_local if repository_local.exists() else FLEET_DEFAULT_PATH


def resolved_allowlist(root: Path, explicit: Path | None) -> tuple[Identity, ...]:
    """The validated allowlist at the configured path.

    With the fleet default always packaged, the configured path is missing
    only when ``explicit`` or ``COMMIT_IDENTITY_ALLOWLIST`` names a path that
    does not exist; that is still :class:`~pipelines_hooks.core.errors.Unavailable`
    (a fail-closed CI exit, a visible local skip naming the remedy). A present
    but malformed file is :class:`~pipelines_hooks.core.errors.CannotRun` (always
    exit 2), since that is a defect in the input, not an absent prerequisite.
    """
    path = configured_path(root, explicit)
    if not path.exists():
        raise Unavailable(f"the commit identity allowlist {path} is not installed", remedy=REMEDY)
    try:
        return load_allowlist(path)
    except (OSError, IdentityAllowlistError) as exc:
        raise CannotRun(f"cannot load the commit identity allowlist ({type(exc).__name__}: {exc})") from exc
