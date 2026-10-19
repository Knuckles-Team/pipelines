"""The wheel-only connector Dockerfile renderer is deterministic and source-free."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "connector_dockerfile.py"
spec = importlib.util.spec_from_file_location("connector_dockerfile", SCRIPT)
assert spec and spec.loader
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

PYPROJECT = """
[project]
name = "demo-mcp"
version = "1.2.3"
[project.optional-dependencies]
mcp = []
agent = []
[project.scripts]
demo-mcp = "demo.mcp:main"
demo-agent = "demo.agent:main"
"""

SOURCE_DOCKERFILE = """FROM python:3.14-slim AS builder
COPY . /src
RUN pip install "/src[mcp]"
FROM python:3.14-slim AS mcp
ARG HOST=0.0.0.0
ARG PORT=9000
USER 10001:10001
CMD ["demo-mcp"]
FROM python:3.14-slim AS agent
CMD ["demo-agent"]
FROM python:3.14-slim AS gone
CMD ["demo-gone"]
"""


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "demo-mcp"
    (repo / "docker").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(PYPROJECT)
    (repo / "docker" / "Dockerfile").write_text(SOURCE_DOCKERFILE)
    return repo


def test_render_installs_published_wheel_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    out = renderer.render(repo)
    assert "COPY . " not in out
    assert '"demo-mcp[mcp]==1.2.3"' in out
    assert '"demo-mcp[agent]==1.2.3"' in out
    assert out.count("--only-binary :all: \\\n") == 2
    assert "python:3.14-slim@sha256:" in out
    assert "ARG HOST=0.0.0.0" in out and "ARG PORT=9000" in out
    assert 'CMD ["demo-mcp"]' in out and 'CMD ["demo-agent"]' in out
    assert "USER 10001:10001" in out
    assert "cargo" not in out


def test_render_is_idempotent(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    first = renderer.render(repo)
    (repo / "docker" / "Dockerfile").write_text(first)
    assert renderer.render(repo) == first


def test_stage_without_shipped_entrypoint_is_dropped(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "pyproject.toml").write_text(PYPROJECT.replace('demo-agent = "demo.agent:main"\n', ""))
    out = renderer.render(repo)
    assert "AS agent" not in out
    assert "AS mcp" in out
