"""commit-identity allowlist schema: FR-1 (P-1, N-1).

Every identity here is an obviously synthetic ``*.invalid`` fixture, never a
real contributor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.identity.allowlist import (
    MAX_ALLOWLIST_BYTES,
    IdentityAllowlistError,
    load_allowlist,
    matches,
    validated_terms,
)
from tests.hooks.conftest import write_identity_allowlist

ALLOWED = {"name": "Example Author", "email": "author@example.invalid"}
OTHER = {"name": "Example Reviewer", "email": "reviewer@example.invalid"}


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
