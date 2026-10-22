"""PIPE-GATES-R009: target-local static import boundaries."""

import pytest

from pipelines_hooks.cli import main
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import Repo

POLICY = """[tool.pipelines_hooks]
packages = ["ui"]
[tool.pipelines_hooks.coupling]
forbidden = ["agent_utilities", "epistemic_graph", "arbora", "agent_webui", "agent_terminal_ui"]
allowed = ["arbora.client"]
"""


# spec: PIPE-GATES-R009
@pytest.mark.parametrize(
    "source",
    [
        "import arbora.client\nfrom arbora import client\nfrom arbora.client import Gateway\n",
        "# import agent_utilities\nx = 'import arbora.runtime'\nimport agent_utilities_extra\n",
        "from . import arbora\n",
    ],
)
def test_allowed_imports(repo, source):
    repo.stage({"pyproject.toml": POLICY, "ui/main.py": source})
    assert repo.run("coupling") == 0


@pytest.mark.parametrize(
    "module", ["agent_utilities", "epistemic_graph", "arbora", "arbora.runtime", "agent_webui", "agent_terminal_ui"]
)
@pytest.mark.parametrize("form", ["import {module}", "from {module} import thing"])
def test_forbidden_imports_even_in_adapter(repo, module, form, capsys):
    repo.stage({"pyproject.toml": POLICY, "ui/services/backend_adapter.py": form.format(module=module)})
    assert repo.run("coupling") == 1
    assert "ui/services/backend_adapter.py:1:" in capsys.readouterr().out


def test_target_index_not_ambient_or_generated(repo, tmp_path, monkeypatch):
    repo.stage({"pyproject.toml": POLICY, "ui/main.py": "import agent_utilities"})
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    other = Repo(foreign)
    other.git("init", "-q")
    other.stage({"ui/clean.py": "pass"})
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(foreign))
    monkeypatch.setenv("GIT_INDEX_FILE", str(foreign / ".git" / "index"))
    assert main(["coupling", "--root", str(repo.root)]) == 1
    repo.write("ui/main.py", "import arbora.client")
    repo.write("ui/generated.py", "import agent_utilities")
    assert repo.run("coupling") == 0


@pytest.mark.parametrize(
    "policy,source",
    [
        ("[tool.pipelines_hooks]\npackages=['ui']", "pass"),
        (POLICY.replace('packages = ["ui"]', 'packages = ["missing"]'), "pass"),
        (POLICY.replace('["arbora.client"]', '["arbora"]'), "pass"),
        (POLICY, "def invalid(:"),
    ],
)
def test_untrustworthy_inputs_refuse(repo, policy, source):
    repo.stage({"pyproject.toml": policy, "ui/main.py": source})
    assert repo.run("coupling") == 2


def test_missing_or_subdirectory_root_refuses(repo):
    repo.stage({"pyproject.toml": POLICY, "ui/main.py": "pass"})
    assert main(["coupling", "--root", str(repo.root / "ui")]) == 2
    assert main(["coupling", "--root", str(repo.root / "missing")]) == 2


def test_untracked_only_package_refuses(repo):
    repo.write("pyproject.toml", POLICY)
    repo.write("ui/main.py", "pass")
    assert repo.run("coupling") == 2


def test_git_scan_failure_refuses(repo, monkeypatch):
    repo.stage({"pyproject.toml": POLICY, "ui/main.py": "pass"})

    def failed(*args, **kwargs):
        raise CannotRun("index unavailable")

    monkeypatch.setattr("pipelines_hooks.code.coupling.tracked_paths", failed)
    assert repo.run("coupling") == 2


def test_from_parent_does_not_allow_nonclient(repo):
    repo.stage({"pyproject.toml": POLICY, "ui/main.py": "from arbora import client, runtime"})
    assert repo.run("coupling") == 1
