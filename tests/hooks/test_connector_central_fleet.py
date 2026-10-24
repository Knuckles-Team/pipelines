"""The connector repository set comes from workspace.yml and active GitHub repositories (PIPE-GATES-R016.44)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.hygiene.connector_central import fleet

MANIFEST = """name: w
subdirectories:
  agent-packages:
    repositories:
      - url: "https://github.com/Knuckles-Team/agent-utilities.git"
    subdirectories:
      agents:
        repositories:
          - url: "https://github.com/Knuckles-Team/alpha-api.git"
          - url: "https://github.com/Knuckles-Team/beta-mcp.git"
          - url: "https://github.com/Knuckles-Team/retired-api.git"
"""


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    path = tmp_path / "workspace.yml"
    path.write_text(MANIFEST, encoding="utf-8")
    return path


@pytest.mark.spec("PIPE-GATES-R016.44")
def test_the_set_is_the_agents_group_of_the_manifest(manifest: Path) -> None:
    assert fleet.workspace_connectors(manifest) == ["alpha-api", "beta-mcp", "retired-api"]


@pytest.mark.spec("PIPE-GATES-R016.44")
def test_an_archived_repository_is_excluded_and_an_unlisted_local_checkout_never_enters(manifest: Path) -> None:
    active = lambda: {"alpha-api", "beta-mcp", "stale-local-checkout", "agent-utilities"}  # noqa: E731 - retired-api is archived
    assert fleet.connector_repos(manifest, active) == ["alpha-api", "beta-mcp"]
    assert fleet.only_active(["alpha-api", "retired-api", "stale-local-checkout"], manifest, active) == ["alpha-api"]
