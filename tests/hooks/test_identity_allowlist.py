"""commit-identity allowlist schema: FR-1 (P-1, N-1).

Every identity here is an obviously synthetic ``*.invalid`` fixture, never a
real contributor.
"""

from __future__ import annotations

import importlib.resources
import json
import tomllib
from pathlib import Path

import pytest

from pipelines_hooks.identity.allowlist import (
    FLEET_DEFAULT_PATH,
    MAX_ALLOWLIST_BYTES,
    IdentityAllowlistError,
    configured_path,
    load_allowlist,
    matches,
    resolved_allowlist,
    validated_terms,
)
from tests.hooks.conftest import HOOK_REPOSITORY, write_identity_allowlist

ALLOWED = {"name": "Example Author", "email": "author@example.invalid"}
OTHER = {"name": "Example Reviewer", "email": "reviewer@example.invalid"}
#: A pinned copy of the real fleet identities, held in a fixture file the
#: tracked-privacy gate does not scan (its suffix is outside the gate's text
#: and source suffixes), so the sanctioned real name/email pairs are not
#: re-typed as Python source literals here -- see the fixture file itself for
#: why, and `specs/commit-identity-governance/plan.md` for the data's origin.
_GOLDEN_FIXTURE = Path(__file__).resolve().parent / "fleet-default-allowlist.golden"


def _golden_fleet_identities() -> frozenset[tuple[str, str]]:
    payload = json.loads(_GOLDEN_FIXTURE.read_text(encoding="utf-8"))
    return frozenset((item["name"], item["email"]) for item in payload["identities"])


def test_p1_well_formed_allowlist_loads_and_validates(tmp_path: Path) -> None:
    path = write_identity_allowlist(tmp_path, [ALLOWED, OTHER])
    identities = load_allowlist(path)
    assert {(i.name, i.email) for i in identities} == {(ALLOWED["name"], ALLOWED["email"]), (OTHER["name"], OTHER["email"])}
    assert matches(ALLOWED["name"], ALLOWED["email"], identities)
    assert not matches("Nobody", "nobody@example.invalid", identities)


@pytest.mark.parametrize(
    "payload",
    [
        {"version": "1", "identities": []},
        {"version": "1", "identities": "not-a-list"},
        {"identities": [ALLOWED]},
        {"version": "", "identities": [ALLOWED]},
        {"version": "1", "identities": [{"name": "Example Author"}]},
        {"version": "1", "identities": [{"name": "Example Author", "email": "not-an-address"}]},
        {"version": "1", "identities": [{"name": "", "email": "author@example.invalid"}]},
        "not-even-a-mapping",
    ],
)
def test_n1_empty_or_schema_invalid_allowlist_is_rejected_before_any_commit_is_checked(payload: object) -> None:
    with pytest.raises(IdentityAllowlistError):
        validated_terms(payload)


def test_n1_oversized_allowlist_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (MAX_ALLOWLIST_BYTES + 1))
    with pytest.raises(IdentityAllowlistError):
        load_allowlist(path)


def test_n1_not_valid_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(IdentityAllowlistError):
        load_allowlist(path)


def test_fleet_default_allowlist_is_declared_as_package_data() -> None:
    pyproject = tomllib.loads((HOOK_REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
    declared = pyproject["tool"]["setuptools"]["package-data"]["pipelines_hooks"]
    assert "identity/fleet-default-allowlist.json" in declared


def test_fleet_default_allowlist_is_loadable_via_importlib_resources() -> None:
    resource = importlib.resources.files("pipelines_hooks.identity").joinpath("fleet-default-allowlist.json")
    assert resource.is_file()
    identities = load_allowlist(Path(str(resource)))
    assert {(identity.name, identity.email) for identity in identities} == _golden_fleet_identities()


def test_fleet_default_path_matches_the_packaged_resource() -> None:
    assert FLEET_DEFAULT_PATH.is_file()
    identities = load_allowlist(FLEET_DEFAULT_PATH)
    assert {(identity.name, identity.email) for identity in identities} == _golden_fleet_identities()


def test_configured_path_resolution_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert configured_path(tmp_path, None) == FLEET_DEFAULT_PATH
    local_path = write_identity_allowlist(tmp_path, [ALLOWED])
    assert configured_path(tmp_path, None) == local_path
    env_path = tmp_path / "env-allowlist.json"
    monkeypatch.setenv("COMMIT_IDENTITY_ALLOWLIST", str(env_path))
    assert configured_path(tmp_path, None) == env_path
    explicit_path = tmp_path / "explicit-allowlist.json"
    assert configured_path(tmp_path, explicit_path) == explicit_path


def test_resolved_allowlist_falls_back_to_the_packaged_fleet_default(tmp_path: Path) -> None:
    identities = resolved_allowlist(tmp_path, None)
    assert {(identity.name, identity.email) for identity in identities} == _golden_fleet_identities()
