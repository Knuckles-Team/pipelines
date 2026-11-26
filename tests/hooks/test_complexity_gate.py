"""PIPE-GATES-R106: one shared complexity hook, configured by [tool.complexity]."""

from __future__ import annotations

import pytest
import yaml

from pipelines_hooks.cli import GATES
from pipelines_hooks.complexity import gate
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import HOOK_REPOSITORY, Repo


@pytest.mark.spec("PIPE-GATES-R106")
def test_one_complexity_hook_reads_the_tool_complexity_table(repo: Repo, capsys) -> None:
    ids = [hook["id"] for hook in yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text())]
    assert ids.count("complexity") == 1 and not [i for i in ids if i.startswith("complexity-")]
    assert GATES["complexity"] == "pipelines_hooks.complexity.gate"
    assert not {"complexity-staged", "complexity-census"} & set(GATES)  # a hard cutover: no alias
    for body in ("[tool.complexity]\nmax_cyclomatic = 20\n", "[tool.complexity]\ncensus = 'yes'\n"):
        repo.write("pyproject.toml", body)
        with pytest.raises(CannotRun):
            gate.table(repo.root)
        assert repo.run("complexity") == 2  # the caps are fixed and the table is typed
    repo.write("pyproject.toml", '[tool.complexity]\ncensus = true\ncensus_paths = ["pkg"]\n')
    assert dict(gate.table(repo.root)) == {"census": True, "census_paths": ["pkg"]}
    repo.write("pyproject.toml", "[project]\nname = 'x'\n")
    assert gate.table(repo.root) == {}
