"""PIPE-CONNSPEC-R018: the CITY- prefix belongs to arbora-city."""

from __future__ import annotations


from pipelines_hooks.specs import repository_identity
from tests.hooks.conftest import Repo

_ROWS = "| ID | Requirement |\n|---|---|\n| CITY-PACKAGE-R001 | One. |\n| CITY-PACKAGE-R002 | Two. |\n"


def test_the_city_prefix_resolves_to_arbora_city(repo: Repo) -> None:
    # spec: PIPE-CONNSPEC-R018
    assert repository_identity._OWNER_PREFIXES["CITY"] == "arbora-city"
    repo.write("specs/demo/requirements.md", _ROWS)
    assert repository_identity.declared_owner(repo.root) == "arbora-city"
