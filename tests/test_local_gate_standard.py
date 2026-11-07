"""PIPE-RELEASE-R029: the attested local gate and the local release are written rules, not habits."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def section(path: str, heading: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    start = text.index(heading)
    level = heading.split(" ", 1)[0]
    rest = text[start + len(heading) :]
    ends = [i for i in (rest.find(f"\n{level} "), rest.find("\n## ")) if i >= 0]
    return rest[: min(ends)] if ends else rest


@pytest.mark.spec("PIPE-RELEASE-R029.1")
def test_ci_standard_states_the_attested_local_gate() -> None:
    text = section("reference/ci-standard.md", "## Attested local gate")
    for required in (
        "pre-commit configs and stages",
        "CI-only config",
        "full test suite",
        "type checks",
        "Cargo checks",
        "merge of the head with the base",
        "also fails on the base commit",
        "`CI required`",
        "comments the full evidence",
        "--match-head-commit",
        "name no host, private domain or local path",
        "pull-request bypass",
        "A direct push to main still needs the status",
        "only after the merge",
    ):
        assert required in text, required
    releases = section("reference/ci-standard.md", "## Auto-merge and releases (keep it simple)")
    assert "Nothing publishes on red CI" in releases
    assert "counts as that commit's green CI" in releases


@pytest.mark.spec("PIPE-RELEASE-R029.2")
def test_release_readiness_states_the_local_release_order() -> None:
    text = section("reference/python-release-readiness.md", "### Local release")
    steps = [
        "green `CI required` status",
        "Build the sdist and the wheel locally",
        "release readiness checks locally",
        "push the tag",
        "skip files that already exist",
        "Create the GitHub release",
        "fresh virtual environment and import",
    ]
    positions = [text.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "macOS and Windows wheels stay on the hosted release" in text
    assert "PIPE-RELEASE-R029.3" in text
