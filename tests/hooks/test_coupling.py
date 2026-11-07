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


LAYER_POLICY = """[tool.pipelines_hooks]
packages = ["app"]
[tool.pipelines_hooks.coupling]
layers = ["app.types", ["app.core", "app.store"], "app.api", "app"]
"""
BASE = {
    "app/__init__.py": "",
    "app/types/__init__.py": "X = 1\n",
    "app/core/__init__.py": "",
    "app/store/__init__.py": "",
    "app/api/__init__.py": "",
}


def _layers(repo, extra, capsys, policy=LAYER_POLICY):
    repo.stage({"pyproject.toml": policy, **BASE, **extra})
    code = repo.run("coupling")
    return code, capsys.readouterr().out


# spec: PIPE-GATES-R088
@pytest.mark.parametrize(
    "source",
    [
        "from app.types import X\n",
        "import app.types\n",
        "from app import types\n",
        "from ..types import X\n",
        "from app.store import thing\n",  # peer layer, same rank
    ],
)
def test_import_direction_follows_layers_downward_passes(repo, capsys, source):
    code, out = _layers(repo, {"app/core/m.py": source}, capsys)
    assert (code, out) == (0, "")


# spec: PIPE-GATES-R088
@pytest.mark.parametrize(
    "path,source",
    [
        ("app/types/m.py", "from app.core import thing\n"),
        ("app/core/m.py", "import app.api.routes\n"),
        ("app/core/m.py", "from .. import api\n"),
        ("app/types/m.py", "from ..api.routes import r\n"),
    ],
)
def test_import_direction_follows_layers_upward_fails(repo, capsys, path, source):
    code, out = _layers(repo, {path: source}, capsys)
    assert code == 1
    assert f"{path}:1:" in out and "less stable layer" in out


# spec: PIPE-GATES-R088
@pytest.mark.parametrize("source", ["from app.store._internal import x\n", "from app.store import _helper\n"])
def test_private_module_reach_fails_and_own_unit_passes(repo, capsys, source):
    extra = {"app/store/_internal.py": "x = 1\n", "app/store/_helper.py": "y = 1\n", "app/api/m.py": source}
    code, out = _layers(repo, extra, capsys)
    assert code == 1
    assert "app/api/m.py:1: import of private module" in out
    repo.write("app/api/m.py", "x = 1\n")
    repo.write("app/store/m.py", "from app.store._internal import x\nfrom ._helper import y\n")
    repo.git("add", "--", "app/api/m.py", "app/store/m.py")
    assert repo.run("coupling") == 0


# spec: PIPE-GATES-R088
def test_unlayered_unit_is_a_finding(repo, capsys):
    code, out = _layers(repo, {"app/extra/m.py": "x = 1\n"}, capsys)
    assert code == 1
    assert "app/extra/m.py:1: unit app.extra is named in no layer" in out


# spec: PIPE-GATES-R088
def test_unit_cycle_is_reported_by_unit(repo, capsys):
    # Two peer units importing each other: neither import is upward, only the cycle is reported.
    peer = LAYER_POLICY
    code, out = _layers(
        repo, {"app/core/m.py": "from app.store import a\n", "app/store/m.py": "from app.core import b\n"}, capsys, peer
    )
    assert code == 1
    assert "import cycle among units app.core, app.store" in out
    assert "less stable" not in out


# spec: PIPE-GATES-R088
@pytest.mark.parametrize(
    "layers", ['"app.types", "app.types"', '"not a name"', "3"], ids=["duplicate", "bad-name", "bad-type"]
)
def test_layers_policy_fault_refuses(repo, layers):
    policy = f'[tool.pipelines_hooks]\npackages = ["app"]\n[tool.pipelines_hooks.coupling]\nlayers = [{layers}]\n'
    repo.stage({"pyproject.toml": policy, **BASE})
    assert repo.run("coupling") == 2


# spec: PIPE-GATES-R088
def test_import_direction_follows_layers(repo, capsys):
    code, out = _layers(repo, {"app/api/m.py": "from app.types import X\n"}, capsys)
    assert (code, out) == (0, "")
    repo.write("app/types/m.py", "from app.api.m import y\n")
    repo.git("add", "--", "app/types/m.py")
    assert repo.run("coupling") == 1
    assert "app/types/m.py:1:" in capsys.readouterr().out
