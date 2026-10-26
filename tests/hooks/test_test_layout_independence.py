"""Focused source proofs for PIPE-PAGES-R039.1-.6."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pipelines_hooks.ci_replica import test_layout
from pipelines_hooks.ci_replica.test_layout import ProjectLayout, TestLayoutPolicy
from pipelines_hooks.ci_replica.test_layout_inventory import MAX_OUTPUT_BYTES, MAX_TIMEOUT_SECONDS
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import Repo


def _project() -> ProjectLayout:
    return ProjectLayout.from_mapping(
        {
            "name": "fixture-project",
            "unit_module_roots": ["tests/unit"],
            "integration_module_roots": ["tests/integration"],
            "shared_fixture_locations": ["tests/conftest.py"],
            "required_category_modules": ["pkg/unit.py", "pkg/integration.py"],
            "isolation_boundaries": ["state"],
            "reset_contracts": ["state"],
        }
    )


def _policy() -> TestLayoutPolicy:
    return TestLayoutPolicy(projects=(_project(),), shuffle_seeds=(11, 29), timeout_seconds=3.0)


def _populate(repo: Repo) -> None:
    repo.commit(
        {
            "pkg/unit.py": "VALUE = 'unit'\n",
            "pkg/integration.py": "VALUE = 'integration'\n",
            "tests/conftest.py": "# shared fixture declaration\n",
            "tests/unit/test_unit.py": "def test_unit(): pass\n",
            "tests/integration/test_integration.py": "def test_integration(): pass\n",
            "state/marker": "reset\n",
        },
        "layout fixture",
    )


def _collector(_root: Path, files: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{path}::test_case" for path in files)


def test_test_layout_independence_model() -> None:
    # spec: PIPE-PAGES-R039.1
    project = _project()
    assert project.unit_module_roots == ("tests/unit",)
    assert project.integration_module_roots == ("tests/integration",)
    assert project.shared_fixture_locations == ("tests/conftest.py",)
    assert project.required_category_modules == ("pkg/unit.py", "pkg/integration.py")
    policy = _policy()
    assert policy.shuffle_seeds == (11, 29)
    assert policy.timeout_seconds == 3.0
    assert test_layout.policy_digest(policy).startswith("sha256:")


def test_test_layout_independence_rejects_duplicate_seeds() -> None:
    # spec: PIPE-PAGES-R039.1
    with pytest.raises(CannotRun, match="distinct"):
        TestLayoutPolicy.from_mapping({"projects": [_project().__dict__], "shuffle_seeds": [11, 11]})
    with pytest.raises(CannotRun, match="timeout_seconds"):
        TestLayoutPolicy.from_mapping({"projects": [_project().__dict__], "timeout_seconds": MAX_TIMEOUT_SECONDS + 1})


def test_test_layout_independence_behavior_uses_four_isolated_orders(repo: Repo) -> None:
    # spec: PIPE-PAGES-R039.2
    _populate(repo)
    calls: list[tuple[Path, tuple[str, ...]]] = []

    def runner(root: Path, tests: tuple[str, ...], _timeout: float) -> dict[str, str]:
        calls.append((root, tests))
        return {test: "passed" for test in tests}

    report = test_layout.check(repo.root, _policy(), collector=_collector, runner=runner)
    assert report.status == 0
    assert len(calls) == 4
    assert len({root for root, _ in calls}) == 4
    assert all(root != repo.root for root, _ in calls)
    assert len(report.projects[0].orders) == 4


def test_test_layout_independence_applies_policy_timeout_to_default_collection(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: PIPE-PAGES-R039.2
    _populate(repo)
    observed: list[float] = []

    def collector(_root: Path, files: tuple[str, ...], timeout: float) -> tuple[str, ...]:
        observed.append(timeout)
        return _collector(_root, files)

    monkeypatch.setattr(test_layout, "_default_collector", collector)
    report = test_layout.check(
        repo.root,
        _policy(),
        runner=lambda _root, tests, _timeout: {test: "passed" for test in tests},
    )
    assert report.status == 0
    assert observed == [3.0]


def test_test_layout_independence_uses_selected_index_over_dirty_worktree(repo: Repo) -> None:
    # spec: PIPE-PAGES-R039.2
    _populate(repo)
    repo.stage({"pkg/unit.py": "VALUE = 'staged'\n"})
    repo.write("pkg/unit.py", "VALUE = 'dirty'\n")
    seen: list[str] = []

    def runner(root: Path, tests: tuple[str, ...], _timeout: float) -> dict[str, str]:
        seen.append((root / "pkg/unit.py").read_text(encoding="utf-8"))
        return {test: "passed" for test in tests}

    report = test_layout.check(repo.root, _policy(), collector=_collector, runner=runner)
    assert report.status == 0
    assert report.source_ref.startswith("index:")
    assert seen == ["VALUE = 'staged'\n"] * 4


def test_test_layout_independence_refuses_missing_declared_fixture(repo: Repo) -> None:
    # spec: PIPE-PAGES-R039.4
    _populate(repo)
    project = ProjectLayout.from_mapping(
        {
            **_project().__dict__,
            "shared_fixture_locations": ["tests/conftest.py", "tests/missing_fixture.py"],
        }
    )
    report = test_layout.check(repo.root, TestLayoutPolicy(projects=(project,)), collector=_collector)
    assert report.status == 1
    assert "required fixture is unavailable" in report.findings[0]


def test_test_layout_independence_refuses_order_dependency(repo: Repo) -> None:
    # spec: PIPE-PAGES-R039.2
    _populate(repo)

    def runner(_root: Path, tests: tuple[str, ...], _timeout: float) -> dict[str, str]:
        status = "passed" if tests[0].startswith("tests/integration") else "failed"
        return {test: status for test in tests}

    report = test_layout.check(repo.root, _policy(), collector=_collector, runner=runner)
    assert report.status == 1
    assert any("depend on order" in finding for finding in report.findings)


def test_test_layout_independence_refuses_consistent_test_failure(repo: Repo) -> None:
    # spec: PIPE-PAGES-R039.2
    _populate(repo)
    report = test_layout.check(
        repo.root,
        _policy(),
        collector=_collector,
        runner=lambda _root, tests, _timeout: {test: "failed" for test in tests},
    )
    assert report.status == 1
    assert any("did not all pass" in finding for finding in report.findings)


def test_test_layout_independence_timeout_is_unavailable(repo: Repo) -> None:
    # spec: PIPE-PAGES-R039.4
    _populate(repo)

    def runner(_root: Path, tests: tuple[str, ...], _timeout: float) -> dict[str, str]:
        return {test: "timeout" for test in tests}

    report = test_layout.check(repo.root, _policy(), collector=_collector, runner=runner)
    assert report.status == 2
    assert any("timed-out" in finding for finding in report.findings)


def test_test_layout_independence_evidence_binds_inventory_orders_and_digests(repo: Repo) -> None:
    # spec: PIPE-PAGES-R039.5
    _populate(repo)
    report = test_layout.check(
        repo.root,
        _policy(),
        collector=_collector,
        runner=lambda _root, tests, _timeout: {test: "passed" for test in tests},
    )
    payload = report.to_dict()
    project = payload["projects"][0]
    assert payload["policy_digest"].startswith("sha256:")
    assert payload["source_ref"].startswith("index:")
    assert project["source_digest"].startswith("sha256:")
    assert project["fixtures"] == ["tests/conftest.py"]
    assert project["unit_module_roots"] == ["tests/unit"]
    assert project["integration_module_roots"] == ["tests/integration"]
    assert project["integration_modules"] == ["tests/integration/test_integration.py"]
    assert project["collected_tests"]
    assert [order["name"] for order in project["orders"]] == ["declared", "reverse", "seed-11", "seed-29"]
    assert all(order["outcomes"] for order in project["orders"])


def test_test_layout_independence_cli_entry_uses_real_fixture_and_emits_receipt(
    repo: Repo, tmp_path: Path, monkeypatch
) -> None:
    # spec: PIPE-PAGES-R039.6
    _populate(repo)
    policy_path = repo.write(
        ".config/test-layout.json",
        json.dumps(
            {
                "version": 1,
                "projects": [_project().__dict__],
                "shuffle_seeds": [11, 29],
                "timeout_seconds": 3,
            }
        ),
    )
    repo.git("add", "--", ".config/test-layout.json")
    monkeypatch.setattr(test_layout, "_default_collector", _collector)
    monkeypatch.setattr(
        test_layout,
        "_default_runner",
        lambda _root, tests, _timeout: {test: "passed" for test in tests},
    )
    evidence = tmp_path / "layout-report.json"
    assert (
        test_layout.main(["--root", str(repo.root), "--inventory", str(policy_path), "--evidence", str(evidence)]) == 0
    )
    receipt = json.loads(evidence.read_text(encoding="utf-8"))
    assert receipt["status"] == 0
    assert len(receipt["projects"][0]["orders"]) == 4


@pytest.mark.parametrize(
    ("junit", "test_count"),
    [(None, 1), ("<testsuite><testcase", 1), ("<testsuite><testcase /></testsuite>", 2)],
)
def test_test_layout_independence_refuses_missing_or_truncated_junit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, junit: str | None, test_count: int
) -> None:
    # spec: PIPE-PAGES-R039.4
    project = tmp_path / "project"
    project.mkdir()

    def fake_run(command, _cwd, _timeout):
        report = Path(next(item.removeprefix("--junitxml=") for item in command if item.startswith("--junitxml=")))
        if junit is not None:
            report.write_text(junit, encoding="utf-8")
        return test_layout._BoundedResult(0, "", "")

    monkeypatch.setattr(test_layout, "_run_bounded", fake_run)
    with pytest.raises(CannotRun, match="missing or malformed|incomplete"):
        test_layout._default_runner(
            project, tuple(f"tests/unit/test_case.py::test_case_{index}" for index in range(test_count)), 1.0
        )


def test_test_layout_independence_bounds_child_output_and_timeout(tmp_path: Path) -> None:
    # spec: PIPE-PAGES-R039.4
    with pytest.raises(CannotRun, match="exceeded"):
        test_layout._run_bounded(
            [sys.executable, "-c", f"import sys; sys.stdout.write('x' * {MAX_OUTPUT_BYTES + 1})"],
            tmp_path,
            2.0,
        )
    result = test_layout._run_bounded([sys.executable, "-c", "import time; time.sleep(2)"], tmp_path, 0.05)
    assert result.timed_out
