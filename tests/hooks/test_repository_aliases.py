"""Repository refs are compared by their current slug; retired slugs are not translated."""

from pipelines_hooks.core.repositories import canonical_repository, repository_matches
from pipelines_hooks.specs.priority import train_rank


def test_canonical_repository_normalizes_refs_without_renaming_slugs() -> None:
    assert canonical_repository("https://github.com/Knuckles-Team/scion-sdk.git") == "Knuckles-Team/scion-sdk"
    assert canonical_repository("agent-utilities") == "agent-utilities"


def test_repository_matches_current_refs_without_cross_owner_match() -> None:
    assert repository_matches("Knuckles-Team/overstory", "overstory")
    assert not repository_matches("agent-webui", "overstory")
    assert not repository_matches("Other-Team/overstory", "Knuckles-Team/overstory")


def test_priority_ranks_current_slugs_only() -> None:
    assert train_rank("medulla") == 0
    assert train_rank("scion-sdk") == 1
    assert train_rank("meristem") == 2
    assert train_rank("overstory") == 4
    assert train_rank("epistemic-graph") == train_rank("not-a-repository")
