"""supply-chain fires on unpinned sources and passes pinned ones."""

from __future__ import annotations

from tests.hooks.conftest import Repo

SHA = "34e114876b0b11c390a56381ad16ebd13914f8d5"
PINNED_WORKFLOW = (
    "name: ci\non: push\npermissions:\n  contents: read\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n"
    f"      - uses: actions/checkout@{SHA}\n        with:\n          persist-credentials: false\n"
)


def test_supply_chain_passes_pinned_sources(repo: Repo) -> None:
    repo.commit({".github/workflows/ci.yml": PINNED_WORKFLOW, "uv.lock": "version = 1\n"})
    assert repo.run("supply-chain", str(repo.root)) == 0


def test_supply_chain_fires_on_an_unpinned_action_and_missing_permissions(repo: Repo, capsys) -> None:
    unpinned = PINNED_WORKFLOW.replace(f"@{SHA}", "@v4").replace("permissions:\n  contents: read\n", "")
    repo.commit({".github/workflows/ci.yml": unpinned, "uv.lock": "version = 1\n"})
    assert repo.run("supply-chain", str(repo.root)) == 1
    output = capsys.readouterr().out
    assert "SC-GHA-001" in output and "SC-GHA-002" in output


def test_supply_chain_fires_on_a_missing_lock_an_unpinned_hook_and_an_unpinned_image(repo: Repo, capsys) -> None:
    repo.commit(
        {
            ".pre-commit-config.yaml": "repos:\n- repo: https://github.com/example/hooks\n  rev: v1.0.0\n  hooks:\n  - id: x\n",
            "docker/Dockerfile": "FROM python:3.12-slim\n",
        }
    )
    assert repo.run("supply-chain", str(repo.root)) == 1
    output = capsys.readouterr().out
    assert all(rule in output for rule in ("SC-DEP-001", "SC-HOOK-001", "SC-CTR-001"))
