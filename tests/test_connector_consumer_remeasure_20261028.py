"""Main-bound re-measure of the connector spec-delivery leaves (2026-10-28).

The register published ``SPECIFIED`` for 46 connector leaves that the adoption
sweep of 2026-10-27/28 had already delivered on the connectors' ``main``: the
spec-delivery adoption PRs added the hooks, the Pages caller and the rapid
delivery section, and the connector-standard migration then rewrote the hook
block to the shared aggregate ``spec`` hook.

The fixture is the exact content of each consumer file on that consumer's
current ``origin/main``, read read-only through the GitHub API, with the commit
that last touched each file. These tests replay the requirement predicates over
those bytes: no network call, no consumer checkout, no consumer code executed.
A leaf is claimed only where the predicate holds for the recorded bytes, and the
claimed set is pinned below, so an over-claim fails here rather than on the page.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from pipelines_hooks.cli import GROUPS


FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/consumer_train_r103_r161_remeasure.json"
SKILL_HEADING = "Rapid delivery: the 5-minute contract"
PAGES_CALLER = "pages_pipeline.yml@main"
PAGES_DASHBOARD = "spec_dashboard_enabled: true"
SPEC_LEAVES = ("spec-status", "spec-decomposition", "spec-trailers")
PIPELINES_REPO = re.compile(r"^\s*- repo: https://github\.com/Knuckles-Team/pipelines\s*(?:#.*)?$", re.M)
AGGREGATE_HOOK = re.compile(r"^\s*- id: spec\s*$", re.M)
SHA = re.compile(r"^[0-9a-f]{40}$")

EXPECTED_HOOK_ROWS = {
    "PIPE-CONNSPEC-R103.2",
    "PIPE-CONNSPEC-R111.2",
    "PIPE-CONNSPEC-R118.2",
    "PIPE-CONNSPEC-R124.2",
    "PIPE-CONNSPEC-R125.2",
    "PIPE-CONNSPEC-R131.2",
    "PIPE-CONNSPEC-R136.2",
    "PIPE-CONNSPEC-R139.2",
    "PIPE-CONNSPEC-R140.2",
    "PIPE-CONNSPEC-R142.2",
    "PIPE-CONNSPEC-R143.2",
    "PIPE-CONNSPEC-R147.2",
    "PIPE-CONNSPEC-R150.2",
    "PIPE-CONNSPEC-R151.2",
    "PIPE-CONNSPEC-R152.2",
    "PIPE-CONNSPEC-R155.2",
    "PIPE-CONNSPEC-R161.2",
}
EXPECTED_PAGES_ROWS = {
    "PIPE-CONNSPEC-R118.3",
    "PIPE-CONNSPEC-R122.3",
    "PIPE-CONNSPEC-R123.3",
    "PIPE-CONNSPEC-R124.3",
    "PIPE-CONNSPEC-R131.3",
    "PIPE-CONNSPEC-R133.3",
    "PIPE-CONNSPEC-R136.3",
    "PIPE-CONNSPEC-R139.3",
    "PIPE-CONNSPEC-R142.3",
    "PIPE-CONNSPEC-R143.3",
    "PIPE-CONNSPEC-R150.3",
    "PIPE-CONNSPEC-R151.3",
    "PIPE-CONNSPEC-R155.3",
    "PIPE-CONNSPEC-R156.3",
}
EXPECTED_SKILL_ROWS = {
    "PIPE-CONNSPEC-R118.4",
    "PIPE-CONNSPEC-R123.4",
    "PIPE-CONNSPEC-R124.4",
    "PIPE-CONNSPEC-R131.4",
    "PIPE-CONNSPEC-R136.4",
    "PIPE-CONNSPEC-R137.4",
    "PIPE-CONNSPEC-R139.4",
    "PIPE-CONNSPEC-R140.4",
    "PIPE-CONNSPEC-R142.4",
    "PIPE-CONNSPEC-R143.4",
    "PIPE-CONNSPEC-R147.4",
    "PIPE-CONNSPEC-R150.4",
    "PIPE-CONNSPEC-R151.4",
    "PIPE-CONNSPEC-R156.4",
    "PIPE-CONNSPEC-R157.4",
}
EXPECTED_LEAVES = EXPECTED_HOOK_ROWS | EXPECTED_PAGES_ROWS | EXPECTED_SKILL_ROWS
#: Measured on main and deliberately left out: the row's predicate is false there.
HELD_ROWS = {"PIPE-CONNSPEC-R157.2"}


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _files(row: dict) -> dict[str, dict]:
    return row["files"]


def _precommit(row: dict) -> str:
    paths = [path for path in _files(row) if path.endswith(("pre-commit-config.yaml", "pre-commit.yaml"))]
    assert len(paths) == 1, paths
    return paths[0]


def _pages(row: dict) -> str:
    paths = [path for path in _files(row) if path == ".github/workflows/pages.yml"]
    assert len(paths) == 1, paths
    return paths[0]


def _skills(row: dict) -> list[str]:
    return [path for path in _files(row) if path.endswith("/SKILL.md") and "development" in path]


def _pipelines_block(text: str) -> str:
    match = PIPELINES_REPO.search(text)
    if not match:
        return ""
    end = text.find("- repo:", match.end())
    return text[match.start() : end if end > 0 else len(text)]


def _hook_evidence(text: str) -> tuple[bool, str]:
    block = _pipelines_block(text)
    if not block:
        return False, "no Knuckles-Team/pipelines block"
    if AGGREGATE_HOOK.search(block):
        return True, "aggregate spec hook"
    missing = [hook for hook in SPEC_LEAVES if f"id: {hook}" not in block]
    return (not missing), "missing " + ",".join(missing)


def _pages_evidence(text: str) -> bool:
    return PAGES_CALLER in text and PAGES_DASHBOARD in text


def _skill_evidence(row: dict) -> bool:
    return any(SKILL_HEADING in _files(row)[path]["content"] for path in _skills(row))


def _claimed(evidence: dict) -> dict[str, str]:
    return {rid: repo for repo, row in evidence["repos"].items() for rid in row["leaves"]}


def test_shared_spec_hook_is_the_canonical_three_hook_mapping() -> None:
    """A `.2` row may only be bound when the shared aggregate equals the three leaves."""
    evidence = _evidence()
    provider = evidence["provider"]
    assert list(GROUPS["spec"]) == provider["spec_group"]
    assert set(provider["spec_group"]) == {"spec-standard", "plan-conformance", *SPEC_LEAVES}
    assert provider["canonical_template_rev"] == "main"


def test_recorded_evidence_is_content_addressed_and_main_bound() -> None:
    evidence = _evidence()
    for repo, row in evidence["repos"].items():
        assert SHA.match(row["main_sha"]), repo
        assert re.fullmatch(r"PIPE-CONNSPEC-R\d{3}", row["row"]), repo
        assert set(row["leaves"]) <= {f"{row['row']}{suffix}" for suffix in (".2", ".3", ".4")}
        for path, item in _files(row).items():
            content = item["content"]
            assert item["path"] == path
            assert item["bytes"] == len(content.encode())
            assert item["sha256"] == hashlib.sha256(content.encode()).hexdigest()
            assert SHA.match(item["last_commit"]), (repo, path)


@pytest.mark.spec("PIPE-CONNSPEC-R103.2")
@pytest.mark.spec("PIPE-CONNSPEC-R111.2")
@pytest.mark.spec("PIPE-CONNSPEC-R118.2")
@pytest.mark.spec("PIPE-CONNSPEC-R124.2")
@pytest.mark.spec("PIPE-CONNSPEC-R125.2")
@pytest.mark.spec("PIPE-CONNSPEC-R131.2")
@pytest.mark.spec("PIPE-CONNSPEC-R136.2")
@pytest.mark.spec("PIPE-CONNSPEC-R139.2")
@pytest.mark.spec("PIPE-CONNSPEC-R140.2")
@pytest.mark.spec("PIPE-CONNSPEC-R142.2")
@pytest.mark.spec("PIPE-CONNSPEC-R143.2")
@pytest.mark.spec("PIPE-CONNSPEC-R147.2")
@pytest.mark.spec("PIPE-CONNSPEC-R150.2")
@pytest.mark.spec("PIPE-CONNSPEC-R151.2")
@pytest.mark.spec("PIPE-CONNSPEC-R152.2")
@pytest.mark.spec("PIPE-CONNSPEC-R155.2")
@pytest.mark.spec("PIPE-CONNSPEC-R161.2")
def test_hook_rows_carry_the_shared_spec_hook_on_main() -> None:
    evidence = _evidence()
    claimed = _claimed(evidence)
    assert {rid for rid in claimed if rid.endswith(".2")} == EXPECTED_HOOK_ROWS
    for rid in EXPECTED_HOOK_ROWS:
        repo = claimed[rid]
        row = evidence["repos"][repo]
        proven, why = _hook_evidence(_files(row)[_precommit(row)]["content"])
        assert proven, f"{rid} ({repo}): {why}"


@pytest.mark.spec("PIPE-CONNSPEC-R118.3")
@pytest.mark.spec("PIPE-CONNSPEC-R122.3")
@pytest.mark.spec("PIPE-CONNSPEC-R123.3")
@pytest.mark.spec("PIPE-CONNSPEC-R124.3")
@pytest.mark.spec("PIPE-CONNSPEC-R131.3")
@pytest.mark.spec("PIPE-CONNSPEC-R133.3")
@pytest.mark.spec("PIPE-CONNSPEC-R136.3")
@pytest.mark.spec("PIPE-CONNSPEC-R139.3")
@pytest.mark.spec("PIPE-CONNSPEC-R142.3")
@pytest.mark.spec("PIPE-CONNSPEC-R143.3")
@pytest.mark.spec("PIPE-CONNSPEC-R150.3")
@pytest.mark.spec("PIPE-CONNSPEC-R151.3")
@pytest.mark.spec("PIPE-CONNSPEC-R155.3")
@pytest.mark.spec("PIPE-CONNSPEC-R156.3")
def test_pages_rows_call_the_reusable_workflow_and_publish_a_site() -> None:
    evidence = _evidence()
    claimed = _claimed(evidence)
    assert {rid for rid in claimed if rid.endswith(".3")} == EXPECTED_PAGES_ROWS
    for rid in EXPECTED_PAGES_ROWS:
        repo = claimed[rid]
        row = evidence["repos"][repo]
        assert _pages_evidence(_files(row)[_pages(row)]["content"]), f"{rid} ({repo})"
        assert row["pages_site"] == f"https://knuckles-team.github.io/{repo}/", f"{rid} ({repo})"


@pytest.mark.spec("PIPE-CONNSPEC-R118.4")
@pytest.mark.spec("PIPE-CONNSPEC-R123.4")
@pytest.mark.spec("PIPE-CONNSPEC-R124.4")
@pytest.mark.spec("PIPE-CONNSPEC-R131.4")
@pytest.mark.spec("PIPE-CONNSPEC-R136.4")
@pytest.mark.spec("PIPE-CONNSPEC-R137.4")
@pytest.mark.spec("PIPE-CONNSPEC-R139.4")
@pytest.mark.spec("PIPE-CONNSPEC-R140.4")
@pytest.mark.spec("PIPE-CONNSPEC-R142.4")
@pytest.mark.spec("PIPE-CONNSPEC-R143.4")
@pytest.mark.spec("PIPE-CONNSPEC-R147.4")
@pytest.mark.spec("PIPE-CONNSPEC-R150.4")
@pytest.mark.spec("PIPE-CONNSPEC-R151.4")
@pytest.mark.spec("PIPE-CONNSPEC-R156.4")
@pytest.mark.spec("PIPE-CONNSPEC-R157.4")
def test_skill_rows_carry_the_rapid_delivery_section_on_main() -> None:
    evidence = _evidence()
    claimed = _claimed(evidence)
    assert {rid for rid in claimed if rid.endswith(".4")} == EXPECTED_SKILL_ROWS
    for rid in EXPECTED_SKILL_ROWS:
        repo = claimed[rid]
        row = evidence["repos"][repo]
        assert _skills(row), f"{rid} ({repo}): no development skill file"
        assert _skill_evidence(row), f"{rid} ({repo})"


def test_only_measured_rows_are_claimed_and_all_were_specified_before() -> None:
    evidence = _evidence()
    claimed = _claimed(evidence)
    assert set(claimed) == EXPECTED_LEAVES
    assert len(set(claimed)) == len(claimed) == 46
    assert set(evidence["register_before"]) == EXPECTED_LEAVES | HELD_ROWS
    assert set(evidence["register_before"].values()) == {"SPECIFIED"}
    assert not HELD_ROWS & EXPECTED_LEAVES
    for repo, row in evidence["repos"].items():
        hooks, _ = _hook_evidence(_files(row)[_precommit(row)]["content"])
        if f"{row['row']}.2" in EXPECTED_HOOK_ROWS:
            assert hooks, repo
        if f"{row['row']}.2" not in EXPECTED_HOOK_ROWS:
            assert f"{row['row']}.2" not in row["leaves"], repo


def test_repository_manager_hook_row_stays_unqualified() -> None:
    """`repository-manager` pins the provider and lists one hook, so R157.2 is not delivered."""
    evidence = _evidence()
    row = evidence["held"]["repository-manager"]
    assert row["leaves"] == []
    assert row["row"] == "PIPE-CONNSPEC-R157"
    block = _pipelines_block(_files(row)[_precommit(row)]["content"])
    assert "rev: main" not in block
    assert AGGREGATE_HOOK.search(block) is None
    assert "id: spec-status" in block
    for hook in ("spec-decomposition", "spec-trailers"):
        assert f"id: {hook}" not in block
