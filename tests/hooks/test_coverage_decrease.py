"""coverage-decrease refuses a proposal whose measured coverage falls below its baseline (PIPE-GATES-R049)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.cli import GATES, main
from pipelines_hooks.code.coverage_decrease import (
    CoverageEvidence,
    compare,
    parse_evidence,
    render_evidence,
)
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import HOOK_REPOSITORY, Repo


def _measure(percent: object, revision: str, tool: str = "coverage-py") -> dict:
    return {"percent": percent, "revision": revision, "tool": tool}


def _evidence(root: Path, baseline: object, candidate: object) -> Path:
    path = root.parent / "evidence.json"
    path.write_text(json.dumps({"baseline": baseline, "candidate": candidate}), encoding="utf-8")
    return path


def _history(repo: Repo) -> tuple[str, str]:
    first = repo.commit({"pkg/a.py": "a = 1\n"}, "first")
    return first, repo.commit({"pkg/b.py": "b = 2\n"}, "second")


@pytest.mark.spec("PIPE-GATES-R049.1")
def test_evidence_holds_percent_revision_and_tool(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps({"baseline": _measure("81.50", "aaa"), "candidate": _measure(82.1, "bbb", "tool-x")}))
    baseline, candidate = parse_evidence(path)
    assert baseline == CoverageEvidence(Decimal("81.50"), "aaa", "coverage-py")
    assert candidate == CoverageEvidence(Decimal("82.1"), "bbb", "tool-x")
    for bad in (_measure(None, "a"), _measure("101", "a"), _measure("x", "a"), _measure(True, "a"), _measure("5", "")):
        path.write_text(json.dumps({"baseline": bad, "candidate": _measure("5", "b")}))
        with pytest.raises(CannotRun):
            parse_evidence(path)
    path.write_text("not json")
    with pytest.raises(CannotRun):
        parse_evidence(path)


@pytest.mark.spec("PIPE-GATES-R049.2")
def test_a_lower_candidate_fails_and_an_equal_one_passes(repo: Repo) -> None:
    first, second = _history(repo)
    base = CoverageEvidence(Decimal("80.00"), first, "t")
    assert compare(base, CoverageEvidence(Decimal("79.99"), second, "t")) == ["coverage fell from 80.00% to 79.99%"]
    assert compare(base, CoverageEvidence(Decimal("80.0"), second, "t")) == []
    assert compare(base, CoverageEvidence(Decimal("80.01"), second, "t")) == []
    path = _evidence(repo.root, _measure("80.00", first), _measure("79.99", second))
    assert repo.run("coverage-decrease", "--evidence", str(path)) == 1
    path = _evidence(repo.root, _measure("80.00", first), _measure("80.00", second))
    assert repo.run("coverage-decrease", "--evidence", str(path)) == 0


@pytest.mark.spec("PIPE-GATES-R049.3")
def test_the_gate_is_a_published_hook() -> None:
    assert GATES["coverage-decrease"] == "pipelines_hooks.code.coverage_decrease"
    hooks = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    entries = {hook["id"]: hook["entry"] for hook in hooks}
    assert entries["coverage-decrease"] == "pipelines-hook coverage-decrease"


@pytest.mark.spec("PIPE-GATES-R049.4")
def test_an_absent_measurement_cannot_run_and_a_stale_baseline_fails(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second = _history(repo)
    assert repo.run("coverage-decrease") == 2
    assert repo.run("coverage-decrease", "--evidence", str(repo.root.parent / "missing.json")) == 2
    path = _evidence(repo.root, None, _measure("90", second))
    assert repo.run("coverage-decrease", "--evidence", str(path)) == 2
    path = _evidence(repo.root, _measure("90", first), {})
    assert repo.run("coverage-decrease", "--evidence", str(path)) == 2
    assert "CANNOT RUN" in capsys.readouterr().err
    # The baseline is not an ancestor of the candidate: the candidate measured the older revision.
    path = _evidence(repo.root, _measure("70", second), _measure("90", first))
    assert repo.run("coverage-decrease", "--evidence", str(path)) == 1
    assert "not an ancestor" in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R049.5")
def test_the_evidence_line_is_deterministic_and_names_both_revisions() -> None:
    base = CoverageEvidence(Decimal("80.5"), "rev-a", "t")
    cand = CoverageEvidence(Decimal("81"), "rev-b", "t")
    line = render_evidence("proposal-1", base, cand)
    assert line == render_evidence("proposal-1", base, cand)
    record = json.loads(line)
    assert list(record) == sorted(record)
    assert record == {
        "baseline_percent": "80.5",
        "baseline_revision": "rev-a",
        "candidate_percent": "81",
        "candidate_revision": "rev-b",
        "proposal": "proposal-1",
    }


@pytest.mark.spec("PIPE-GATES-R049.6")
def test_a_planted_decrease_is_rejected_through_the_cli(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    first, second = _history(repo)
    path = _evidence(repo.root, _measure("91.25", first), _measure("88.10", second))
    code = main(["coverage-decrease", "--root", str(repo.root), "--evidence", str(path), "--proposal", "p-9"])
    out = capsys.readouterr().out
    assert code == 1
    assert "91.25" in out and "88.10" in out and '"proposal":"p-9"' in out
    clean = _evidence(repo.root, _measure("91.25", first), _measure("91.30", second))
    assert main(["coverage-decrease", "--root", str(repo.root), "--evidence", str(clean)]) == 0
