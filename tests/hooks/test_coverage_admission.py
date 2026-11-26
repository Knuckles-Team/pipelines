"""PIPE-PAGES-R040: coverage-decrease refusal at Meristem proposal admission.

The one mechanism is the ``coverage-decrease`` gate (PIPE-GATES-R049); these tests prove the
admission-facing behaviour through its real command line on a real Git history.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.code.coverage_decrease import CoverageEvidence, compare, parse_evidence
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import Repo


def _measure(percent: object, revision: str) -> dict[str, object]:
    return {"percent": percent, "revision": revision, "tool": "coverage-py"}


def _write(root: Path, baseline: object, candidate: object) -> Path:
    path = root / "evidence.json"
    path.write_text(json.dumps({"baseline": baseline, "candidate": candidate}), encoding="utf-8")
    return path


def _history(tmp_path: Path) -> tuple[Repo, str, str]:
    repo = Repo(tmp_path / "repo")
    repo.root.mkdir()
    repo.git("init", "-q")
    first = repo.commit({"pkg/a.py": "a = 1\n"}, "first")
    return repo, first, repo.commit({"pkg/b.py": "b = 2\n"}, "second")


# spec: PIPE-PAGES-R040.1
def test_evidence_carries_baseline_candidate_and_revision(tmp_path: Path) -> None:
    baseline, candidate = parse_evidence(_write(tmp_path, _measure("80.5", "aaa"), _measure(81, "bbb")))
    assert baseline == CoverageEvidence(Decimal("80.5"), "aaa", "coverage-py")
    assert (candidate.percent, candidate.revision) == (Decimal(81), "bbb")
    for missing in (None, {"percent": "80", "revision": "aaa"}, {"revision": "a", "tool": "t"}):
        with pytest.raises(CannotRun):
            parse_evidence(_write(tmp_path, missing, _measure(81, "bbb")))
    with pytest.raises(CannotRun):
        parse_evidence(_write(tmp_path, _measure(80, "aaa"), None))


# spec: PIPE-PAGES-R040.2
def test_decrease_is_rejected_deterministically() -> None:
    high, low = CoverageEvidence(Decimal("80.50"), "a", "t"), CoverageEvidence(Decimal("80.49"), "b", "t")
    assert [compare(high, low) for _ in range(3)] == [compare(high, low)] * 3
    assert compare(high, low) and not compare(low, high) and not compare(high, high)


# spec: PIPE-PAGES-R040.3
def test_gate_is_registered_and_binds_the_revision(tmp_path: Path) -> None:
    assert GATES["coverage-decrease"] == "pipelines_hooks.code.coverage_decrease"
    repo, first, second = _history(tmp_path)
    assert (
        repo.run("coverage-decrease", "--evidence", str(_write(tmp_path, _measure(80, first), _measure(80, second))))
        == 0
    )
    # The baseline measured at a revision that is not an ancestor of the candidate is stale.
    assert (
        repo.run("coverage-decrease", "--evidence", str(_write(tmp_path, _measure(80, second), _measure(80, first))))
        == 1
    )


# spec: PIPE-PAGES-R040.4
def test_missing_or_stale_evidence_fails_instead_of_passing(tmp_path: Path) -> None:
    repo, first, second = _history(tmp_path)
    unmeasured = _write(tmp_path, {"revision": first, "tool": "coverage-py"}, _measure(90, second))
    assert repo.run("coverage-decrease", "--evidence", str(unmeasured)) == 2
    assert repo.run("coverage-decrease") == 2
    unknown = _write(tmp_path, _measure(80, "0" * 40), _measure(80, second))
    assert repo.run("coverage-decrease", "--evidence", str(unknown)) == 2
    stale = _write(tmp_path, _measure(80, second), _measure(95, first))
    assert repo.run("coverage-decrease", "--evidence", str(stale)) == 1


# spec: PIPE-PAGES-R040.5
def test_evidence_line_names_the_proposal_and_both_measurements(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, first, second = _history(tmp_path)
    path = _write(tmp_path, _measure("80.00", first), _measure("79.00", second))
    assert repo.run("coverage-decrease", "--evidence", str(path), "--proposal", "prop-7") == 1
    line = json.loads(capsys.readouterr().out.splitlines()[0])
    assert line == {
        "baseline_percent": "80.00",
        "baseline_revision": first,
        "candidate_percent": "79.00",
        "candidate_revision": second,
        "proposal": "prop-7",
    }


# spec: PIPE-PAGES-R040.6
def test_planted_decrease_exits_one(tmp_path: Path) -> None:
    repo, first, second = _history(tmp_path)
    planted = _write(tmp_path, _measure("82.00", first), _measure("81.99", second))
    assert repo.run("coverage-decrease", "--evidence", str(planted), "--proposal", "p") == 1
    equal = _write(tmp_path, _measure("82.00", first), _measure("82.00", second))
    assert repo.run("coverage-decrease", "--evidence", str(equal), "--proposal", "p") == 0
