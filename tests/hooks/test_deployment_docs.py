"""PIPE-PAGES-R020.49 to R020.54: the four deployment patterns match the owner export."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.docs import deployment_docs as dd
from pipelines_hooks.docs.gate_io import sha
from tests.hooks.conftest import Repo
from tests.hooks.docs_support import fetch, serve

EXPORT = "docs/deployment-export.json"


def export() -> dict:
    return {
        "format": "deployment-export/1",
        "owner": "fixture-owner",
        "runtime": "docker",
        "patterns": {
            "uv-stdio": {
                "status": "supported",
                "capability": "cap.stdio",
                "transport": "stdio",
                "package": "fixture-mcp",
                "config": {"path": "docs/mcp/uv-stdio.json", "pointer": "/mcpServers/fixture"},
                "argv": ["uvx", "fixture-mcp"],
                "env": {"FIXTURE_TOKEN": "${FIXTURE_TOKEN}"},
                "prerequisites": ["uv"],
            },
            "uv-local-http": {
                "status": "supported",
                "capability": "cap.http",
                "transport": "streamable-http",
                "package": "fixture-mcp",
                "config": {"path": "docs/mcp/uv-local-http.json", "pointer": "/mcpServers/fixture"},
                "argv": ["uvx", "fixture-mcp", "--transport", "http"],
                "env": {},
                "prerequisites": ["uv"],
            },
            "local-container-http": {
                "status": "supported",
                "capability": "cap.container",
                "transport": "http",
                "image": "registry.example/fixture:1",
                "config": {"path": "docs/mcp/container.json", "pointer": "/mcpServers/fixture"},
                "argv": ["docker", "run", "--rm", "-p", "8000:8000", "registry.example/fixture:1"],
                "env": {},
                "prerequisites": ["docker"],
            },
            "remote-container-url": {
                "status": "supported",
                "capability": "cap.remote",
                "transport": "streamable-http",
                "config": {"path": "docs/mcp/remote.json", "pointer": "/mcpServers/fixture"},
                "owner_argv": ["docker", "run", "--rm", "registry.example/fixture:1"],
                "env": {},
                "prerequisites": [],
            },
        },
    }


CONFIGS = {
    "docs/mcp/uv-stdio.json": {
        "mcpServers": {
            "fixture": {"command": "uvx", "args": ["fixture-mcp"], "env": {"FIXTURE_TOKEN": "${FIXTURE_TOKEN}"}}
        }
    },
    "docs/mcp/uv-local-http.json": {"mcpServers": {"fixture": {"url": "http://127.0.0.1:8000/mcp"}}},
    "docs/mcp/container.json": {"mcpServers": {"fixture": {"url": "http://localhost:8000/mcp"}}},
    "docs/mcp/remote.json": {"mcpServers": {"fixture": {"url": "https://fixture.example.com/mcp"}}},
}
README = """# Fixture

### uv-stdio

```bash
uvx fixture-mcp
```

### uv-local-http

```bash
uvx fixture-mcp --transport http
```

### local-container-http

```bash
docker run --rm -p 8000:8000 registry.example/fixture:1
```

### remote-container-url

Connect with the url in the configuration. The owner host starts it:

```bash owner-host
docker run --rm registry.example/fixture:1
```

## Next
"""


def build(tmp_path: Path, exp: dict | None = None, readme: str = README, configs: dict | None = None) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.root.mkdir(parents=True)
    repo.git("init", "-q")
    raw = json.dumps(exp or export(), indent=1)
    files = {path: json.dumps(cfg) for path, cfg in (configs or CONFIGS).items()}
    decl = {"schema": 1, "export": EXPORT, "export_digest": sha(raw), "readme": "README.md"}
    repo.stage({EXPORT: raw, "README.md": readme, dd.DECLARATION: json.dumps(decl), **files})
    return repo


def with_config(path: str, doc: dict) -> dict:
    return {**CONFIGS, path: doc}


# spec: PIPE-PAGES-R020.49
def test_deployment_docs_model(tmp_path: Path) -> None:
    matrix = dd.load_matrix(build(tmp_path).root)
    assert set(matrix.patterns) == set(dd.PATTERNS) and matrix.runtime == "docker"
    stdio = matrix.patterns["uv-stdio"]
    assert (stdio.status, stdio.capability, stdio.argv, stdio.config_pointer) == (
        "supported",
        "cap.stdio",
        ("uvx", "fixture-mcp"),
        "/mcpServers/fixture",
    )
    assert matrix.patterns["remote-container-url"].owner_argv[0] == "docker"
    for bad, msg in (
        ({"runtime": "lxc"}, "container runtime"),
        ({"patterns": {**export()["patterns"], "uv-stdio": {"status": "supported"}}}, "capability evidence"),
    ):
        with pytest.raises(CannotRun, match=msg):
            dd.load_matrix(build(tmp_path / msg.split()[0], export() | bad).root)
    fabricated = export()
    fabricated["patterns"]["uv-stdio"]["argv"] = ["uvx", "x | sh"]
    with pytest.raises(CannotRun, match="command grammar"):
        dd.load_matrix(build(tmp_path / "fab", fabricated).root)


# spec: PIPE-PAGES-R020.50
def test_deployment_docs_behavior(tmp_path: Path) -> None:
    assert dd.check(build(tmp_path).root).findings == []
    breakages = {
        "uv-stdio": ("docs/mcp/uv-stdio.json", {"mcpServers": {"fixture": {"command": "uvx", "args": ["other"]}}}),
        "uv-local-http": (
            "docs/mcp/uv-local-http.json",
            {"mcpServers": {"fixture": {"url": "https://prod.example.com/mcp"}}},
        ),
        "local-container-http": (
            "docs/mcp/container.json",
            {"mcpServers": {"fixture": {"command": "docker", "url": "http://localhost:8000/mcp"}}},
        ),
        "remote-container-url": ("docs/mcp/remote.json", {"mcpServers": {"fixture": {"url": "http://10.0.0.5/mcp"}}}),
    }
    for pid, (path, doc) in breakages.items():
        assert dd.check(build(tmp_path / pid, configs=with_config(path, doc)).root).findings, pid
    missing_cfg = {k: v for k, v in CONFIGS.items() if k != "docs/mcp/uv-stdio.json"}
    with pytest.raises(CannotRun):
        dd.check(build(tmp_path / "nocfg", configs=missing_cfg).root)
    for pid, old, new in (
        ("uv-stdio", "uvx fixture-mcp\n", "uvx other-mcp\n"),
        ("uv-local-http", "--transport http", "--transport stdio"),
        (
            "local-container-http",
            "registry.example/fixture:1\n```\n\n### remote",
            "registry.example/other:1\n```\n\n### remote",
        ),
    ):
        assert dd.check(build(tmp_path / f"cmd-{pid}", readme=README.replace(old, new, 1)).root).findings, pid
    hosted_spawn = README.replace(
        "```bash owner-host\n",
        "```bash connect\ndocker run --rm registry.example/fixture:1\n```\n\n```bash owner-host\n",
    )
    assert any("nothing to launch" in f for f in dd.check(build(tmp_path / "spawn", readme=hosted_spawn).root).findings)
    no_owner = README.replace("```bash owner-host", "```text")
    assert any("owner-host" in f for f in dd.check(build(tmp_path / "noowner", readme=no_owner).root).findings)
    leaked = with_config(
        "docs/mcp/uv-stdio.json",
        {"mcpServers": {"fixture": {"command": "uvx", "args": ["fixture-mcp"], "env": {"FIXTURE_TOKEN": "abc123"}}}},
    )
    assert any("sourced" in f for f in dd.check(build(tmp_path / "leak", configs=leaked).root).findings)


# spec: PIPE-PAGES-R020.51
def test_deployment_docs_wiring(tmp_path: Path) -> None:
    from pipelines_hooks.cli import GATES, run_gate

    assert GATES["deployment-docs"] == "pipelines_hooks.docs.deployment_docs"
    root = Path(__file__).resolve().parents[2]
    assert "entry: pipelines-hook deployment-docs" in (root / ".pre-commit-hooks.yaml").read_text()
    workflow = (root / ".github/workflows/pages_pipeline.yml").read_text()
    assert workflow.index("docs.deployment_docs") < workflow.index("Upload artifact")
    repo = build(tmp_path)
    assert run_gate("deployment-docs", ["--root", str(repo.root)]) == 0 == repo.run("deployment-docs")


# spec: PIPE-PAGES-R020.52
def test_deployment_docs_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = export()
    del missing["patterns"]["uv-local-http"]
    repo = build(tmp_path / "m", missing)
    assert repo.run("deployment-docs") == 1
    assert "missing ['uv-local-http']" in capsys.readouterr().out
    for name, mutate in {
        "transport": lambda e: e["patterns"]["uv-stdio"].update(transport="carrier-pigeon"),
        "capability": lambda e: e["patterns"]["uv-stdio"].pop("capability"),
        "grammar": lambda e: e["patterns"]["uv-stdio"].update(argv=["uvx", "a;b"]),
    }.items():
        e = export()
        mutate(e)
        assert build(tmp_path / name, e).run("deployment-docs") == 2, name
    constrained = export()
    constrained["patterns"]["local-container-http"] = {
        "status": "constrained",
        "reason": "owner ships no image",
        "owner_evidence": "owner-notes#7",
        "capability": "cap.container",
    }
    readme = README.replace(
        "```bash\ndocker run --rm -p 8000:8000 registry.example/fixture:1\n```", "No image is published."
    )
    repo = build(tmp_path / "c", constrained, readme)
    assert repo.run("deployment-docs") == 0
    out = capsys.readouterr().out
    assert "pattern id=local-container-http state=unsupported" in out and "coverage incomplete" in out
    assert build(tmp_path / "c2", constrained, README).run("deployment-docs") == 1  # advertises a command
    constrained["require_runnable"] = True
    assert build(tmp_path / "c3", constrained, readme).run("deployment-docs") == 1
    unreasoned = copy.deepcopy(constrained)
    del unreasoned["patterns"]["local-container-http"]["reason"]
    assert build(tmp_path / "c4", unreasoned, readme).run("deployment-docs") == 1


# spec: PIPE-PAGES-R020.53
def test_deployment_docs_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    assert repo.run("deployment-docs") == 0
    out = capsys.readouterr().out
    for pid in dd.PATTERNS:
        assert f"pattern id={pid} state=supported" in out
    assert "config=docs/mcp/uv-stdio.json#/mcpServers/fixture command=README.md:" in out
    assert "argv=['uvx', 'fixture-mcp']" in out and "prerequisites=['uv']" in out
    assert "matrix owner=fixture-owner digest=" in out and "validation=syntax-and-contract" in out
    assert "runtime-receipt none: documentation parity does not certify a deployment" in out
    e = export() | {"receipts": {"uv-stdio": {"version": "1.2.3", "digest": "abc"}}}
    assert build(tmp_path / "r", e).run("deployment-docs") == 0
    assert "runtime-receipt id=uv-stdio version=1.2.3 digest=abc source=owner" in capsys.readouterr().out
    assert "FIXTURE_TOKEN=abc" not in out


# spec: PIPE-PAGES-R020.54
def test_deployment_docs_cli(tmp_path: Path) -> None:
    repo = build(tmp_path)
    assert repo.run("deployment-docs") == 0
    # The loopback fixture server stands in for the owner's disposable acceptance environment:
    # the documented local http configuration selects the http transport and is observably served.
    served = tmp_path / "served"
    served.mkdir()
    (served / "mcp").write_text("ok")
    with serve(served) as base:
        port = int(base.rsplit(":", 1)[1])
        cfg = with_config(
            "docs/mcp/uv-local-http.json", {"mcpServers": {"fixture": {"url": f"http://127.0.0.1:{port}/mcp"}}}
        )
        live = build(tmp_path / "live", configs=cfg)
        assert live.run("deployment-docs") == 0
        assert (
            fetch(json.loads((live.root / "docs/mcp/uv-local-http.json").read_text())["mcpServers"]["fixture"]["url"])
            == "ok"
        )
    corruptions = {
        "uv-stdio": ("docs/mcp/uv-stdio.json", {"mcpServers": {"fixture": {"command": "uvx", "args": []}}}),
        "uv-local-http": ("docs/mcp/uv-local-http.json", {"mcpServers": {"fixture": {}}}),
        "local-container-http": ("docs/mcp/container.json", {"mcpServers": {"fixture": {"url": "ftp://x"}}}),
        "remote-container-url": ("docs/mcp/remote.json", {"mcpServers": {"fixture": {"command": "x"}}}),
    }
    for pid, (path, doc) in corruptions.items():
        repo.stage({path: json.dumps(doc)})
        assert repo.run("deployment-docs") == 1, pid
        repo.stage({path: json.dumps(CONFIGS[path])})
        assert repo.run("deployment-docs") == 0, pid
