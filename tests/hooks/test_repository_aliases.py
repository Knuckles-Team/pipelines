"""Repository slug aliases preserve stable package and specification identities."""

from pipelines_hooks.core.repositories import canonical_repository, repository_matches, repository_slug
from pipelines_hooks.specs.priority import train_rank


def test_repository_aliases_canonicalize_bare_and_full_refs() -> None:
    assert canonical_repository("agent-utilities") == "meristem"
    assert canonical_repository("https://github.com/Knuckles-Team/agent-connector-sdk.git") == (
        "Knuckles-Team/scion-sdk"
    )
    assert repository_slug("git@github.com:Knuckles-Team/epistemic-graph-server.git") == "medulla-stem"


def test_repository_matches_old_and_new_refs_without_cross_owner_match() -> None:
    assert repository_matches("Knuckles-Team/agent-webui", "Knuckles-Team/overstory")
    assert repository_matches("agent-terminal-ui", "tuig")
    assert not repository_matches("Other-Team/agent-webui", "Knuckles-Team/overstory")


def test_priority_accepts_retired_and_canonical_first_party_slugs() -> None:
    assert train_rank("epistemic-graph") == train_rank("medulla") == 0
    assert train_rank("agent-connector-sdk") == train_rank("scion-sdk") == 1
    assert train_rank("agent-utilities") == train_rank("meristem") == 2
    assert train_rank("agent-webui") == train_rank("overstory") == 4
