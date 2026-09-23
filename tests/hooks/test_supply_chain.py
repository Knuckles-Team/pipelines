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


def test_supply_chain_inspects_a_pre_commit_suite_relocated_under_config(repo: Repo, capsys) -> None:
    repo.commit(
        {
            ".config/pre-commit.yaml": "repos:\n- repo: https://github.com/example/hooks\n  rev: v1.0.0\n  hooks:\n  - id: x\n",
            "uv.lock": "version = 1\n",
        }
    )
    assert repo.run("supply-chain", str(repo.root)) == 1
    assert "SC-HOOK-001" in capsys.readouterr().out


PIPELINES_WORKFLOW = (
    "name: ci\non: push\npermissions:\n  contents: read\njobs:\n  pages:\n    "
    "uses: Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@{ref}\n"
)


def test_supply_chain_accepts_pipelines_at_main_unpinned(repo: Repo) -> None:
    """Knuckles-Team/pipelines is the one sanctioned exception: @main, not a SHA."""
    repo.commit({".github/workflows/ci.yml": PIPELINES_WORKFLOW.format(ref="main"), "uv.lock": "version = 1\n"})
    assert repo.run("supply-chain", str(repo.root)) == 0


def test_supply_chain_rejects_pipelines_pinned_to_a_commit_sha(repo: Repo, capsys) -> None:
    """A SHA pin of pipelines is refused, not merely tolerated as already-pinned."""
    repo.commit({".github/workflows/ci.yml": PIPELINES_WORKFLOW.format(ref=SHA), "uv.lock": "version = 1\n"})
    assert repo.run("supply-chain", str(repo.root)) == 1
    output = capsys.readouterr().out
    assert "SC-GHA-010" in output
    assert "SC-GHA-001" not in output


def test_supply_chain_rejects_pipelines_pinned_to_a_tag(repo: Repo, capsys) -> None:
    repo.commit({".github/workflows/ci.yml": PIPELINES_WORKFLOW.format(ref="v3.0.0"), "uv.lock": "version = 1\n"})
    assert repo.run("supply-chain", str(repo.root)) == 1
    assert "SC-GHA-010" in capsys.readouterr().out


def test_supply_chain_still_requires_a_sha_from_a_third_party_reusable_workflow(repo: Repo, capsys) -> None:
    """The pipelines exception must not leak to other external `uses:` sources."""
    workflow = PIPELINES_WORKFLOW.format(ref="main").replace(
        "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main",
        "someorg/other-pipelines/.github/workflows/pages.yml@main",
    )
    repo.commit({".github/workflows/ci.yml": workflow, "uv.lock": "version = 1\n"})
    assert repo.run("supply-chain", str(repo.root)) == 1
    assert "SC-GHA-001" in capsys.readouterr().out


def test_supply_chain_accepts_the_pipelines_pre_commit_hook_pinned_to_main(repo: Repo) -> None:
    repo.commit(
        {
            ".pre-commit-config.yaml": "repos:\n- repo: https://github.com/Knuckles-Team/pipelines\n  rev: main\n  hooks:\n  - id: x\n",
            "uv.lock": "version = 1\n",
        }
    )
    assert repo.run("supply-chain", str(repo.root)) == 0


def test_supply_chain_rejects_the_pipelines_pre_commit_hook_pinned_to_a_sha(repo: Repo, capsys) -> None:
    repo.commit(
        {
            ".pre-commit-config.yaml": f"repos:\n- repo: https://github.com/Knuckles-Team/pipelines\n  rev: {SHA}\n  hooks:\n  - id: x\n",
            "uv.lock": "version = 1\n",
        }
    )
    assert repo.run("supply-chain", str(repo.root)) == 1
    output = capsys.readouterr().out
    assert "SC-HOOK-003" in output
    assert "SC-HOOK-001" not in output
