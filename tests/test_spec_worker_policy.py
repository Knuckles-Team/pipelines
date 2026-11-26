"""specs/ingest-worker restates no worker policy outside rows that cite their owner (PIPE-GATES-R018)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS, run_gate
from pipelines_hooks.specs.worker_policy import scan_text
from tests.hooks.conftest import Repo  # noqa: I001


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    fixture = Repo(tmp_path / "repo")
    fixture.root.mkdir()
    fixture.git("init", "-q", "-b", "main")
    fixture.commit({"README.md": "# fixture\n"}, "base")
    return fixture


CITED = "| `X-R1` | The floor is 0.36 of memory, 3 GiB, the reserved floor. Owner: MEDULLA-DURABLE-KERNEL-R075. | t |\n"
BARE = "| `X-R2` | The worker keeps a reserved floor of 3 GiB and admits 0.36 of cores. | t |\n"


@pytest.mark.spec("PIPE-GATES-R018")
def test_a_duplicate_value_outside_a_citing_row_fails(repo: Repo) -> None:
    repo.commit({"specs/ingest-worker/requirements.md": CITED + BARE})
    findings = scan_text("specs/ingest-worker/requirements.md", CITED + BARE)
    assert len(findings) == 1 and ":2:" in findings[0]
    assert run_gate("ingest-worker-policy", ["--root", str(repo.root)]) == 1


@pytest.mark.spec("PIPE-GATES-R018")
def test_a_citing_row_passes(repo: Repo) -> None:
    fenced = "```\nreserved floor 3 GiB 0.36\n```\n"
    repo.commit({"specs/ingest-worker/requirements.md": CITED + fenced, "specs/other/requirements.md": BARE})
    assert run_gate("ingest-worker-policy", ["--root", str(repo.root)]) == 0
    assert scan_text("x.md", "Version 10.360 and 13 GiB are unrelated.\n") == []


@pytest.mark.spec("PIPE-GATES-R018")
def test_the_check_is_a_member_of_the_spec_group_and_a_repository_without_the_spec_passes(repo: Repo) -> None:
    assert "ingest-worker-policy" in GROUPS["spec"]
    assert run_gate("ingest-worker-policy", ["--root", str(repo.root)]) == 0
