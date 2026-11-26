"""PIPE-PAGES-R020.19 to R020.24: runtime environment reads, documentation and launcher bindings agree."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.docs import env_documentation as ed
from tests.hooks.conftest import Repo

SOURCE = 'import os\n\nURL = os.environ["SVC_URL"]\nTIMEOUT = os.getenv("SVC_TIMEOUT", "30")\nTOKEN = os.environ.get("SVC_TOKEN")\n'
EXAMPLE = (
    "# [required] Base URL of the service\nSVC_URL=\n"
    "# [optional] Request timeout in seconds\nSVC_TIMEOUT=30\n"
    "# [optional] API token for the service\nSVC_TOKEN=\n"
)
README = (
    "# svc\n\n| Name | Default | Requirement | Purpose |\n|---|---|---|---|\n"
    "| `SVC_URL` | | required | Base URL of the service |\n"
    "| `SVC_TIMEOUT` | `30` | optional | Request timeout in seconds |\n"
    "| `SVC_TOKEN` | | optional | API token for the service |\n"
)
LAUNCHER = {
    "mcpServers": {
        "svc": {"command": "svc", "env": {"SVC_URL": "${SVC_URL}", "SVC_TIMEOUT": "30", "SVC_TOKEN": "${SVC_TOKEN}"}}
    }
}
POLICY = """schema = 1
source_roots = ["pkg"]
example = ".env.example"
readme = "README.md"

[[launcher]]
path = "mcp.json"
identity = "svc"
pointer = "/mcpServers/svc/env"
adapter = "mcp-env-v1"
variables = ["SVC_URL", "SVC_TIMEOUT", "SVC_TOKEN"]
"""


def _repo(tmp_path: Path, **override: str) -> Repo:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    files = {
        ed.DECLARATION: POLICY,
        "pkg/__init__.py": "",
        "pkg/cfg.py": SOURCE,
        ".env.example": EXAMPLE,
        "README.md": README,
        "mcp.json": json.dumps(LAUNCHER, indent=2) + "\n",
    }
    repo.stage({**files, **override})
    return repo


def _launcher(**env: str) -> str:
    data = json.loads(json.dumps(LAUNCHER))
    data["mcpServers"]["svc"]["env"].update(env)
    return json.dumps(data, indent=2) + "\n"


# spec: PIPE-PAGES-R020.19
def test_env_documentation_model(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    policy = ed.load_policy(repo.root)
    uses, digest = ed.discover_reads(repo.root, policy)
    contracts = ed.build_contracts(uses)
    assert digest and sorted(contracts) == ["SVC_TIMEOUT", "SVC_TOKEN", "SVC_URL"]
    assert contracts["SVC_URL"].required and contracts["SVC_URL"].default is None
    assert contracts["SVC_TIMEOUT"].default == "30" and contracts["SVC_TOKEN"].secret
    with pytest.raises(CannotRun):
        ed.RuntimeEnvContract("lower", None, False, False, ())
    with pytest.raises(CannotRun):
        ed.RuntimeEnvContract("API_TOKEN", "x", False, True, ())
    with pytest.raises(CannotRun):
        ed.LauncherEnvBinding("m.json", "s", "/a", "nope-v9", ())
    with pytest.raises(CannotRun):
        ed.LauncherEnvBinding("m.json", "s", "/a", "mcp-env-v1", ("A", "A"))
    clash = _repo(tmp_path / "c", **{"pkg/other.py": 'import os\nos.getenv("SVC_TIMEOUT", "5")\n'})
    with pytest.raises(CannotRun):
        ed.build_contracts(ed.discover_reads(clash.root, ed.load_policy(clash.root))[0])
    bad = _repo(tmp_path / "u", **{ed.DECLARATION: POLICY.replace("schema = 1\n", "schema = 1\nmystery = 1\n")})
    with pytest.raises(CannotRun):
        ed.load_policy(bad.root)


# spec: PIPE-PAGES-R020.20
def test_env_documentation_behavior(tmp_path: Path) -> None:
    assert ed.check(_repo(tmp_path / "ok").root).findings == []
    cases = {
        "example default": {".env.example": EXAMPLE.replace("SVC_TIMEOUT=30", "SVC_TIMEOUT=31")},
        "example requiredness": {".env.example": EXAMPLE.replace("[required]", "[optional]")},
        "readme default": {"README.md": README.replace("`30`", "`31`")},
        "readme purpose": {"README.md": README.replace("Request timeout", "Timeout")},
        "readme missing": {
            "README.md": README.replace("| `SVC_TOKEN` | | optional | API token for the service |\n", "")
        },
        "undocumented read": {"pkg/more.py": 'import os\nos.getenv("SVC_NEW")\n'},
        "launcher missing": {"mcp.json": json.dumps({"mcpServers": {"svc": {"env": {"SVC_URL": "${SVC_URL}"}}}})},
        "launcher default": {"mcp.json": _launcher(SVC_TIMEOUT="99")},
        "launcher secret literal": {"mcp.json": _launcher(SVC_TOKEN="hunter2")},
        "launcher unexpected": {"mcp.json": _launcher(EXTRA="1")},
    }
    for index, (label, change) in enumerate(cases.items()):
        assert ed.check(_repo(tmp_path / f"c{index}", **change).root).findings, label


# spec: PIPE-PAGES-R020.21
def test_env_documentation_wiring(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert GATES["env-documentation"] == "pipelines_hooks.docs.env_documentation"
    hooks = (Path(__file__).resolve().parents[2] / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "entry: pipelines-hook env-documentation" in hooks
    repo = _repo(tmp_path)
    assert repo.run("env-documentation") == 0
    out = capsys.readouterr().out
    assert "doc example name=SVC_URL" in out and "doc readme name=SVC_URL" in out and "launcher path=mcp.json" in out


# spec: PIPE-PAGES-R020.22
def test_env_documentation_refusal(tmp_path: Path) -> None:
    assert _repo(tmp_path / "a", **{"mcp.json": "{ not json"}).run("env-documentation") == 1
    declared_gone = _repo(tmp_path / "b")
    declared_gone.git("rm", "-q", "-f", "mcp.json")
    assert declared_gone.run("env-documentation") == 1
    assert (
        _repo(tmp_path / "c", **{"pkg/dyn.py": 'import os\nname = "X"\nos.environ[name]\n'}).run("env-documentation")
        == 2
    )
    assert _repo(tmp_path / "d", **{"pkg/app.js": "process.env.X\n"}).run("env-documentation") == 2
    assert _repo(tmp_path / "e", **{"mcp.json": _launcher(SVC_TIMEOUT="$(rm -rf /)")}).run("env-documentation") == 2
    assert _repo(tmp_path / "f", **{"other-mcp.json": json.dumps({"mcpServers": {}})}).run("env-documentation") == 2
    guarded = tmp_path / "g"
    marker = guarded / "executed"
    repo = _repo(guarded, **{"pkg/boom.py": f'open({str(marker)!r}, "w")\nimport os\nos.getenv("SVC_TIMEOUT", "30")\n'})
    assert repo.run("env-documentation") == 0 and not marker.exists()
    resolved = _repo(
        tmp_path / "h",
        **{"pkg/dyn.py": 'import os\nfor n in ("SVC_URL",):\n    os.environ[n]\n'},
    )
    assert resolved.run("env-documentation") == 2


# spec: PIPE-PAGES-R020.23
def test_env_documentation_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, **{"pkg/cfg.py": SOURCE + 'API_TOKEN = os.environ.get("SVC_TOKEN", "leaked")\n'})
    assert repo.run("env-documentation") == 1
    out = capsys.readouterr().out
    assert "leaked" not in out and "env name=SVC_TOKEN default=(secret)" in out
    assert "env name=SVC_TIMEOUT default=30 required=False source=pkg/cfg.py:4 provider=os.getenv" in out
    assert (
        "doc example name=SVC_URL line=.env.example:2" in out and "doc readme name=SVC_TIMEOUT line=README.md:6" in out
    )
    launcher = next(line for line in out.splitlines() if line.startswith("launcher "))
    assert (
        "pointer=/mcpServers/svc/env" in launcher and "adapter=mcp-env-v1" in launcher and "SVC_URL=bound" in launcher
    )
    digests = next(line for line in out.splitlines() if line.startswith("digests "))
    assert "source=" in digests and "consumer=" in digests and "policy=" in digests and "unchecked=0" in digests
    missing = _repo(tmp_path / "m", **{"mcp.json": _launcher(SVC_TOKEN="x").replace('"SVC_URL"', '"OTHER"')})
    assert missing.run("env-documentation") == 1
    assert "lacks a binding for SVC_URL" in capsys.readouterr().out


# spec: PIPE-PAGES-R020.24
def test_env_documentation_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert repo.run("env-documentation") == 0
    repo.stage({".env.example": EXAMPLE.replace("[optional] Request", "[required] Request")})
    assert repo.run("env-documentation") == 1
    repo.stage({".env.example": EXAMPLE})
    repo.stage({"README.md": README.replace("`30`", "`31`")})
    assert repo.run("env-documentation") == 1
    repo.stage({"README.md": README})
    repo.stage({"mcp.json": _launcher(SVC_TIMEOUT="9")})
    capsys.readouterr()
    assert repo.run("env-documentation") == 1
    out = capsys.readouterr().out
    assert "mcp.json:" in out and "differs from '30'" in out
    (repo.root / "mcp.json").write_text(json.dumps(LAUNCHER), encoding="utf-8")  # unstaged repair
    assert repo.run("env-documentation") == 1
    repo.stage({"mcp.json": json.dumps(LAUNCHER, indent=2) + "\n"})
    assert repo.run("env-documentation") == 0
    repo.stage({"pkg/dyn.py": "import os\nos.environ[1 + 1]\n"})
    assert repo.run("env-documentation") == 2
