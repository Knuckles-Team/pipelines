"""PIPE-PAGES-R022: scheduled mutation testing reports surviving mutants as test gaps."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipelines_hooks.cli import GATES
from pipelines_hooks.code import mutation_gaps
from pipelines_hooks.code.mutation_gaps import Mutant, MutationPolicy, SurvivingMutation
from pipelines_hooks.core.errors import Unavailable
from tests.hooks.conftest import HOOK_REPOSITORY, Repo

SOURCE = "def small(x):\n    if x < 10:\n        return True\n    return False\n"
LAX_TEST = "from pkg.mod import small\n\n\ndef test_small():\n    assert small(1)\n"
STRICT_TEST = LAX_TEST + "\n\ndef test_large():\n    assert not small(50)\n"
PYPROJECT = (
    '[project]\nname = "fixture"\nversion = "0"\n\n[tool.pipelines_hooks]\npackages = ["pkg"]\n'
    '\n[tool.pipelines_hooks.mutation_gaps]\nmodules = ["pkg"]\n'
)


def _fixture(repo: Repo, test: str, **extra: str) -> None:
    repo.commit(
        {"pyproject.toml": PYPROJECT, "pkg/__init__.py": "", "pkg/mod.py": SOURCE, "tests/test_mod.py": test, **extra}
    )


# spec: PIPE-PAGES-R022.1
def test_policy_defaults() -> None:
    policy = MutationPolicy()
    assert policy.modules == ("pipelines_hooks/core",)
    assert policy.schedule == "weekly"
    assert SurvivingMutation("m.py", 3, "compare Lt->GtE").render() == "m.py:3 compare Lt->GtE"


# spec: PIPE-PAGES-R022.2
def test_only_survivors_are_reported(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    _fixture(repo, LAX_TEST)
    policy = MutationPolicy(modules=("pkg",), root=tmp_path)

    def kill_comparisons(mutant: Mutant) -> bool:
        return mutant.operator.startswith("compare")

    found = mutation_gaps.survivors(policy, kill_comparisons)
    assert found
    assert all(not item.operator.startswith("compare") for item in found)
    assert mutation_gaps.survivors(policy, lambda mutant: True) == []


# spec: PIPE-PAGES-R022.3
def test_mutation_workflow_runs_gate() -> None:
    workflow = yaml.safe_load((HOOK_REPOSITORY / ".github/workflows/mutation.yml").read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["schedule"][0]["cron"]
    steps = [step.get("run", "") for job in workflow["jobs"].values() for step in job["steps"]]
    assert any("pipelines-hook mutation-gaps" in step for step in steps)
    assert GATES["mutation-gaps"] == "pipelines_hooks.code.mutation_gaps"
    hooks = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    assert "pipelines-hook mutation-gaps" in {hook["entry"] for hook in hooks}


# spec: PIPE-PAGES-R022.4
def test_absent_runner_fails_closed_in_ci(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    _fixture(repo, LAX_TEST)
    repo.commit({"pyproject.toml": PYPROJECT + 'test_command = ["no-such-mutation-runner"]\n'})
    monkeypatch.setenv("CI", "1")
    assert repo.run("mutation-gaps") == 2
    monkeypatch.delenv("CI")
    assert repo.run("mutation-gaps") == 0
    with pytest.raises(Unavailable):
        mutation_gaps.SubprocessRunner(
            MutationPolicy(modules=("pkg",), test_command=("no-such-mutation-runner",), root=tmp_path)
        )
    untested = Repo(tmp_path / "untested")
    (tmp_path / "untested").mkdir()
    untested.git("init", "-q")
    untested.commit({"pyproject.toml": PYPROJECT, "pkg/mod.py": SOURCE})
    results = mutation_gaps.evaluate(MutationPolicy(modules=("pkg",), root=untested.root), lambda mutant: True)
    assert [(r.module, r.finding) for r in results] == [("pkg/mod.py", "no-tests-for-module")]


# spec: PIPE-PAGES-R022.5
def test_mutation_report_lines(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    _fixture(repo, LAX_TEST)
    policy = MutationPolicy(modules=("pkg",), root=tmp_path)
    results = mutation_gaps.evaluate(policy, lambda mutant: mutant.operator.startswith("constant"))
    lines = mutation_gaps.render(results)
    assert lines[-1] == "pkg/mod.py: killed 2, survived 1"
    assert lines[0] == "pkg/mod.py:2 compare Lt->GtE"


# spec: PIPE-PAGES-R022.6
def test_mutation_gaps_hook_reports_untested_branch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    _fixture(repo, LAX_TEST)
    assert repo.run("mutation-gaps") == 1
    out = capsys.readouterr().out
    assert "pkg/mod.py:4 constant False->True" in out
    assert "pkg/mod.py: killed" in out
    repo.commit({"tests/test_mod.py": STRICT_TEST})
    assert repo.run("mutation-gaps") == 0
