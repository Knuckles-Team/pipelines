"""workflow-step-honesty refuses a masked test or check step and accepts honest ones (PIPE-GATES-R060)."""

from __future__ import annotations

import pytest

from tests.hooks.conftest import Repo


def _workflow(command: str) -> dict[str, str]:
    body = f"on: push\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - name: run\n        run: |\n          {command}\n"
    return {".github/workflows/ci.yml": body}


@pytest.mark.spec("PIPE-GATES-R060")
@pytest.mark.parametrize(
    "command",
    ["pytest -q || true", "cargo test --all-features ; true", "uv run mypy src || exit 0", "ruff check . || :"],
)
def test_a_masked_test_or_check_step_fails(repo: Repo, command: str) -> None:
    repo.commit(_workflow(command))
    assert repo.run("workflow-step-honesty") == 1


@pytest.mark.spec("PIPE-GATES-R060")
def test_a_mask_on_a_continued_command_fails(repo: Repo) -> None:
    repo.commit(_workflow("cargo nextest run \\\n            --all-features || true"))
    assert repo.run("workflow-step-honesty") == 1


@pytest.mark.spec("PIPE-GATES-R060")
@pytest.mark.parametrize(
    "command",
    ["pytest -q", "cargo test --all-features -p core", "rm -rf build || true", "git fetch origin main || true"],
)
def test_an_honest_step_and_a_masked_cleanup_pass(repo: Repo, command: str) -> None:
    repo.commit(_workflow(command))
    assert repo.run("workflow-step-honesty") == 0
