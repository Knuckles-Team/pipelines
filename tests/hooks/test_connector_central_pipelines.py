"""Central migration rules n to v: pipelines-owned connector boilerplate (PIPE-GATES-R016.91 to .99)."""

from __future__ import annotations

import json
import os
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipelines_hooks.connector import container, generate
from pipelines_hooks.hygiene.connector_central import pipelines as P
from pipelines_hooks.hygiene.connector_central.base import RULES, Ctx, make_ctx

PYPROJECT = """[project]
name = "demo-mcp"
version = "1.2.3"
description = "demo"
dependencies = ["agent-connector-sdk[mcp]>=0.5.2,<0.6.0"]

[project.optional-dependencies]
mcp = []

[project.scripts]
demo-mcp = "demo_mcp.mcp_server:main"

[project.entry-points."agent_connector_sdk.connector"]
demo-mcp = "demo_mcp:connector"

[tool.setuptools.package-data]
demo_mcp = ["ontology/**"]
"""
API = """class DemoApi:
    def a(self):
        return 1

    def b(self):
        return 2
"""
SERVER = """from demo_mcp.api_client import DemoApi

client = DemoApi()


@mcp.tool()
def tool_a():
    return client.a()
"""
TTL = ":Alpha a owl:Class .\n:Beta a owl:Class .\n"
WF_PIPELINE = f"""name: Release
on:
  push:
    branches: [main]
jobs:
  publish-pypi:
    uses: {P.PYTHON_PIPELINE}
    permissions:
      contents: write
  publish-docker:
    needs: publish-pypi
    uses: {P.CONTAINER_PIPELINE}
    permissions:
      contents: read
"""


def old_docker(root: Path) -> None:
    """Commit the container files as the pre-migration generator wrote them (no SDK pin lines, old header)."""
    (root / "docker").mkdir(exist_ok=True)
    for name, text in container.render(root).items():
        text = text.replace("ARG SDK_VERSION=\n", "").replace(" --upgrade-package agent-connector-sdk", "")
        text = text.replace("# GENERATED at build time", "# GENERATED from the old script")
        (root / "docker" / name).write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    pkg = tmp_path / "demo_mcp"
    (pkg / "ontology" / "mappings").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "api_client.py").write_text(API, encoding="utf-8")
    (pkg / "mcp_server.py").write_text(SERVER, encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "pipeline.yml").write_text(WF_PIPELINE, encoding="utf-8")
    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    return tmp_path


def ctx_of(root: Path) -> Ctx:
    ctx = make_ctx(root)
    assert ctx is not None
    return ctx


def run(root: Path, *ids: str) -> Ctx:
    ctx = ctx_of(root)
    for rid in ids:
        RULES[rid](ctx)
    return ctx


def blocking(ctx: Ctx, rid: str) -> list[dict]:
    return [i for i in ctx.review.items if i["step"] == rid and i["blocking"]]


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def ontology(root: Path, classes_in_shapes: list[str] | None = None) -> None:
    pkg = root / "demo_mcp" / "ontology"
    (pkg / "mappings" / "source.yaml").write_text("ontology_source: demo\n", encoding="utf-8")
    (pkg / "demo.ttl").write_text(TTL, encoding="utf-8")
    if classes_in_shapes is not None:
        (pkg / "shapes").mkdir(exist_ok=True)
        (pkg / "shapes" / "connector.shacl.ttl").write_text(generate.shacl("demo", classes_in_shapes), encoding="utf-8")
    else:
        old = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = "0"
        try:
            for path, text in generate.generate(root).items():
                path.write_text(text, encoding="utf-8")
        finally:
            if old is None:
                os.environ.pop("SOURCE_DATE_EPOCH")
            else:
                os.environ["SOURCE_DATE_EPOCH"] = old
        return
    stamp = datetime.fromtimestamp(0, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (pkg / "certification.json").write_text(json.dumps({"validated_at": stamp}), encoding="utf-8")


def toml(root: Path) -> dict:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))


# --- pl.n -------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.91")
def test_n_removes_bumpversion_readme_line_literal_and_test_assertion(repo: Path) -> None:
    (repo / ".bumpversion.cfg").write_text("[bumpversion]\ncurrent_version = 1.2.3\n", encoding="utf-8")
    (repo / "README.md").write_text("# Demo\n\n*Version: 1.2.3*\n\nText\n", encoding="utf-8")
    (repo / "demo_mcp" / "agent_server.py").write_text('__version__ = "1.2.3"\nx = 1\n', encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_startup.py").write_text(
        '"""doc"""\nimport demo_mcp\n\n\ndef test_v():\n    assert demo_mcp.__version__ == "1.2.3"\n', encoding="utf-8"
    )
    ctx = run(repo, "pl.n")
    assert not (repo / ".bumpversion.cfg").exists()
    assert (repo / "README.md").read_text() == "# Demo\n\nText\n"
    assert (repo / "demo_mcp" / "agent_server.py").read_text() == "x = 1\n"
    test = (repo / "tests" / "test_startup.py").read_text()
    assert 'assert importlib.metadata.version("demo-mcp")' in test and "import importlib.metadata\n" in test
    compile(test, "t", "exec")
    assert not ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.91")
def test_n_resolves_dynamic_version_from_bumpversion(repo: Path) -> None:
    text = PYPROJECT.replace('version = "1.2.3"\n', 'dynamic = ["version"]\n') + (
        '\n[tool.setuptools.dynamic]\nversion = {attr = "demo_mcp.__version__"}\n'
    )
    (repo / "pyproject.toml").write_text(text, encoding="utf-8")
    (repo / ".bumpversion.cfg").write_text("[bumpversion]\ncurrent_version = 1.2.3\n", encoding="utf-8")
    ctx = run(repo, "pl.n")
    data = toml(repo)
    assert data["project"]["version"] == "1.2.3" and "dynamic" not in data["project"]
    assert "dynamic" not in data["tool"]["setuptools"]
    assert not blocking(ctx, "pl.n")


@pytest.mark.spec("PIPE-GATES-R016.91")
def test_n_reviews_version_still_read_and_leaves_file(repo: Path) -> None:
    src = '__version__ = "1.2.3"\nprint(__version__)\n'
    (repo / "demo_mcp" / "mcp_server.py").write_text(src, encoding="utf-8")
    ctx = run(repo, "pl.n")
    assert (repo / "demo_mcp" / "mcp_server.py").read_text() == src
    assert blocking(ctx, "pl.n")


# --- pl.o -------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_removes_rendered_files_and_wires_callers(repo: Path) -> None:
    old_docker(repo)
    (repo / "docker" / "starship.toml").write_text("x = 1\n", encoding="utf-8")
    ctx = run(repo, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    for name in container.OUTPUT_FILES:
        assert not (repo / "docker" / name).exists()
    assert (repo / "docker" / "starship.toml").exists()
    ignore = (repo / ".gitignore").read_text()
    assert "docker/Dockerfile\n" in ignore and "docker/*.compose.yml\n" in ignore
    flow = (repo / ".github/workflows/pipeline.yml").read_text()
    assert f"uses: {P.PYTHON_PIPELINE}\n    with:\n      connector: true\n" in flow
    assert f"uses: {P.CONTAINER_PIPELINE}\n    with:\n      render_connector: true\n" in flow
    assert "connector_sdk_rebuild_pipeline.yml@main" in (repo / ".github/workflows/sdk-rebuild.yml").read_text()
    assert "pipelines" not in toml(repo).get("tool", {})


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_ports_exceptions_into_the_container_table(repo: Path) -> None:
    table = {
        "port": 9100,
        "sdist_deps": ["pyaudio"],
        "builder_apt": ["build-essential", "portaudio19-dev"],
        "runtime_apt": ["libportaudio2"],
        "runtime_copies": ["COPY --from=k8s-tools /out/ /usr/local/bin/"],
        "extra_stages": ["FROM alpine AS k8s-tools\nRUN echo hi"],
        "debug_apt": ["ripgrep", "tree"],
        "compose_env": ["EXTRA=1"],
    }
    body = "".join(f"{k} = {P._toml_scalar(v)}\n" for k, v in table.items())
    (repo / "pyproject.toml").write_text(PYPROJECT + f"\n[tool.pipelines.container]\n{body}", encoding="utf-8")
    old_docker(repo)
    (repo / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    ctx = run(repo, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert toml(repo)["tool"]["pipelines"]["container"] == table
    assert not (repo / "docker" / "Dockerfile").exists()


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_unexpected_difference_is_blocking_and_files_stay(repo: Path) -> None:
    old_docker(repo)
    compose = repo / "docker" / "mcp.compose.yml"
    compose.write_text(compose.read_text().replace("pids_limit: 256", "pids_limit: 512"), encoding="utf-8")
    before = snapshot(repo)
    ctx = run(repo, "pl.o")
    assert blocking(ctx, "pl.o") and "512" in blocking(ctx, "pl.o")[0]["detail"]
    assert snapshot(repo) == before


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_accepts_the_dist_extra_that_rule_l4_dropped(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        PYPROJECT.replace("[project.optional-dependencies]\nmcp = []\n", ""), encoding="utf-8"
    )
    old_docker(repo)
    docker = repo / "docker" / "Dockerfile"
    docker.write_text(docker.read_text().replace('"demo-mcp==1.2.3"', '"demo-mcp[mcp]==1.2.3"'), encoding="utf-8")
    dbg = repo / "docker" / "debug.Dockerfile"
    dbg.write_text(re.sub(r"( \.)\s*$", r"\1[mcp]\n", dbg.read_text()), encoding="utf-8")
    ctx = run(repo, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert not docker.exists()
    assert "debug_extras" not in toml(repo).get("tool", {}).get("pipelines", {}).get("container", {})


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_other_extra_difference_stays_blocking(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        PYPROJECT.replace("[project.optional-dependencies]\nmcp = []\n", ""), encoding="utf-8"
    )
    old_docker(repo)
    docker = repo / "docker" / "Dockerfile"
    docker.write_text(docker.read_text().replace('"demo-mcp==1.2.3"', '"demo-mcp[gpu]==1.2.3"'), encoding="utf-8")
    ctx = run(repo, "pl.o")
    assert blocking(ctx, "pl.o") and docker.exists()


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_accepts_a_stale_semver_on_the_dist_own_pin(repo: Path) -> None:
    old_docker(repo)
    docker = repo / "docker" / "Dockerfile"
    assert re.search(r'"demo-mcp(\[mcp\])?==1\.2\.3"', docker.read_text())
    docker.write_text(
        re.sub(r'("demo-mcp(?:\[mcp\])?==)1\.2\.3"', r'\g<1>1.2.2"', docker.read_text()), encoding="utf-8"
    )
    ctx = run(repo, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert not docker.exists()


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_another_package_pin_difference_stays_blocking(repo: Path) -> None:
    old_docker(repo)
    docker = repo / "docker" / "Dockerfile"
    docker.write_text(
        re.sub(r'"demo-mcp(\[mcp\])?==1\.2\.3"', '"other-mcp==1.2.2"', docker.read_text()), encoding="utf-8"
    )
    ctx = run(repo, "pl.o")
    assert blocking(ctx, "pl.o") and docker.exists()


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_ports_compose_limits_only_when_they_differ_from_the_template(repo: Path) -> None:
    old_docker(repo)
    compose = repo / "docker" / "mcp.compose.yml"
    text = compose.read_text()
    text = text.replace("${MCP_CONTAINER_MEMORY_LIMIT:-2g}", "${AGENT_CONTAINER_MEMORY_LIMIT:-4g}")
    text = text.replace("${MCP_CONTAINER_CPU_LIMIT:-1.0}", "${MCP_CONTAINER_CPU_LIMIT:-2.0}")
    compose.write_text(text, encoding="utf-8")
    ctx = run(repo, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert toml(repo)["tool"]["pipelines"]["container"]["limits"] == {
        "mcp": {"memory_limit_env": "AGENT_CONTAINER_MEMORY_LIMIT", "memory_limit": "4g", "cpu_limit": "2.0"}
    }
    out = container.render(repo)["mcp.compose.yml"]
    assert "mem_limit: ${AGENT_CONTAINER_MEMORY_LIMIT:-4g}\n    cpus: ${MCP_CONTAINER_CPU_LIMIT:-2.0}\n" in out


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_default_limits_leave_the_render_and_table_unchanged(repo: Path) -> None:
    old_docker(repo)
    ctx = run(repo, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert "pipelines" not in toml(repo).get("tool", {})
    out = container.render(repo)
    assert (
        "mem_limit: ${MCP_CONTAINER_MEMORY_LIMIT:-2g}\n    cpus: ${MCP_CONTAINER_CPU_LIMIT:-1.0}\n"
        in out["mcp.compose.yml"]
    )


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_container_limits_table_rejects_unknown_keys(repo: Path) -> None:
    from pipelines_hooks.connector import project
    from pipelines_hooks.core.errors import CannotRun

    bad = {"tool": {"pipelines": {"container": {"limits": {"mcp": {"memory": "1g"}}}}}}
    with pytest.raises(CannotRun):
        project.container_table(bad)


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_unknown_workflow_shape_is_blocking(repo: Path) -> None:
    old_docker(repo)
    wf = repo / ".github/workflows/pipeline.yml"
    wf.write_text(
        wf.read_text().replace("    permissions:\n      contents: read", "    with:\n      render_connector: false")
    )
    before = snapshot(repo)
    ctx = run(repo, "pl.o")
    assert blocking(ctx, "pl.o")
    assert snapshot(repo) == before


# --- pl.p -------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.93")
def test_p_removes_generated_artifacts_when_identical(repo: Path) -> None:
    ontology(repo)
    ctx = run(repo, "pl.p")
    assert not ctx.review.items
    assert not (repo / "demo_mcp/ontology/certification.json").exists()
    assert not (repo / "demo_mcp/ontology/shapes/connector.shacl.ttl").exists()
    assert "demo_mcp/ontology/certification.json\n" in (repo / ".gitignore").read_text()


@pytest.mark.spec("PIPE-GATES-R016.93")
def test_p_subset_of_shapes_writes_shape_classes_and_reviews(repo: Path) -> None:
    ontology(repo, ["Alpha"])
    ctx = run(repo, "pl.p")
    assert toml(repo)["tool"]["pipelines"]["ontology"]["shape_classes"] == ["Alpha"]
    assert any(i["step"] == "pl.p" and not i["blocking"] for i in ctx.review.items)
    assert not (repo / "demo_mcp/ontology/shapes/connector.shacl.ttl").exists()


@pytest.mark.spec("PIPE-GATES-R016.93")
def test_p_other_test_reading_artifacts_is_blocking_and_files_stay(repo: Path) -> None:
    ontology(repo)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_parse.py").write_text('p = "certification.json"\n', encoding="utf-8")
    (repo / "tests" / "test_certification_digest.py").write_text('p = "certification.json"\n', encoding="utf-8")
    before = snapshot(repo)
    ctx = run(repo, "pl.p")
    assert blocking(ctx, "pl.p")
    assert snapshot(repo) == before


@pytest.mark.spec("PIPE-GATES-R016.93")
def test_p_deletes_certification_tests(repo: Path) -> None:
    ontology(repo)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_certification_digest.py").write_text('p = "certification.json"\n', encoding="utf-8")
    run(repo, "pl.p")
    assert not (repo / "tests" / "test_certification_digest.py").exists()


# --- pl.q -------------------------------------------------------------------------------------------------------
OLD_HOOKS = """repos:
- repo: https://github.com/pre-commit/pre-commit-hooks
  rev: v6.0.0
  hooks:
  - id: check-yaml
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: v0.1
  hooks:
  - id: ruff-check
    args: ["--ignore=E402"]
- repo: local
  hooks:
  - id: security-sanitizer
    name: s
    entry: python scripts/security_sanitizer.py
    language: system
  - id: my-own-hook
    name: mine
    entry: ./mine.sh
    language: system
"""


@pytest.mark.spec("PIPE-GATES-R016.94")
def test_q_replaces_config_and_lists_unknown_hooks(repo: Path) -> None:
    (repo / ".pre-commit-config.yaml").write_text(OLD_HOOKS, encoding="utf-8")
    ctx = run(repo, "pl.q")
    template = (P.pipelines_root(ctx) / "templates/connector/pre-commit-config.yaml").read_text()
    assert (repo / ".pre-commit-config.yaml").read_text() == template
    details = " ".join(i["detail"] for i in ctx.review.items)
    assert "my-own-hook" in details and "security-sanitizer" not in details and "--ignore=E402" in details
    assert not blocking(ctx, "pl.q")


@pytest.mark.spec("PIPE-GATES-R016.94")
def test_q_unparseable_config_is_noted_and_replaced(repo: Path) -> None:
    (repo / ".pre-commit-config.yaml").write_text("repos: [unclosed\n", encoding="utf-8")
    ctx = run(repo, "pl.q")
    assert any("cannot be scanned" in i["detail"] for i in ctx.review.items)
    assert "connector-standard" in (repo / ".pre-commit-config.yaml").read_text()


# --- pl.r -------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.95")
def test_r_deletes_sanitizer_and_moves_codespell_words(repo: Path) -> None:
    (repo / "scripts").mkdir()
    (repo / "scripts" / "security_sanitizer.py").write_text("# local rule\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_security_sanitizer.py").write_text("import security_sanitizer\n", encoding="utf-8")
    (repo / ".codespellignore").write_text("# c\nzzword\naaword\n", encoding="utf-8")
    ctx = run(repo, "pl.r")
    assert not (repo / "scripts" / "security_sanitizer.py").exists()
    assert not (repo / "tests" / "test_security_sanitizer.py").exists()
    assert not (repo / ".codespellignore").exists()
    assert toml(repo)["tool"]["pipelines"]["codespell"]["ignore_words"] == ["aaword", "zzword"]
    assert any("stale security_sanitizer" in i["detail"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.95")
def test_r_conflicting_codespell_table_is_blocking_and_file_stays(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(PYPROJECT + '\n[tool.pipelines.codespell]\nignore_words = ["other"]\n')
    (repo / ".codespellignore").write_text("zzword\n", encoding="utf-8")
    ctx = run(repo, "pl.r")
    assert blocking(ctx, "pl.r") and (repo / ".codespellignore").exists()


# --- pl.t -------------------------------------------------------------------------------------------------------
CONTRACT = {
    "version": 2,
    "hooks": {},
    "license_policy": {
        "allowed": ["MIT", "PSF-2.0", "zlib-acknowledgement"],
        "allowed_exceptions": ["LLVM-exception"],
        "denied": [],
    },
}


def security_dir(root: Path) -> None:
    (root / ".security").mkdir()
    (root / ".security" / "repository_fuzz.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".security" / "authenticated_negative.py").write_text("x = 2\n", encoding="utf-8")
    (root / ".security" / "security-contract.json").write_text(json.dumps(CONTRACT), encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R016.97")
def test_t_removes_security_dir_and_ports_licenses(repo: Path) -> None:
    security_dir(repo)
    ctx = run(repo, "pl.t")
    assert not (repo / ".security").exists() or not any((repo / ".security").iterdir())
    table = toml(repo)["tool"]["pipelines"]["security"]
    assert table["license_allowed"] == ["PSF-2.0", "zlib-acknowledgement"]
    details = " ".join(i["detail"] for i in ctx.review.items)
    assert "LLVM-exception" in details and "smaller than the shared default" in details


@pytest.mark.spec("PIPE-GATES-R016.97")
def test_t_keeps_contract_when_validator_is_tracked(repo: Path) -> None:
    security_dir(repo)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "security_contract.py").write_text("x = 3\n", encoding="utf-8")
    ctx = run(repo, "pl.t")
    assert (repo / ".security" / "security-contract.json").exists()
    assert not (repo / ".security" / "repository_fuzz.py").exists()
    assert any("security_contract.py" in i["detail"] for i in ctx.review.items)
    assert "pipelines" not in toml(repo).get("tool", {})


# --- pl.u -------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.98")
def test_u_deletes_bootstrap_and_rewrites_setup_line(repo: Path) -> None:
    (repo / "scripts").mkdir()
    (repo / "scripts" / "bootstrap.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("- **Setup:** run `scripts/bootstrap.sh`. It is idempotent.\n- **Gates:** x\n")
    ctx = run(repo, "pl.u")
    assert not (repo / "scripts" / "bootstrap.sh").exists()
    assert (repo / "AGENTS.md").read_text() == f"{P.SETUP}\n- **Gates:** x\n"
    assert not ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.98")
def test_u_other_mention_goes_to_review(repo: Path) -> None:
    (repo / "scripts").mkdir()
    (repo / "scripts" / "bootstrap.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "README.md").write_text("Run ./scripts/bootstrap.sh then work.\n", encoding="utf-8")
    ctx = run(repo, "pl.u")
    assert (repo / "README.md").read_text() == "Run ./scripts/bootstrap.sh then work.\n"
    assert ctx.review.items and not blocking(ctx, "pl.u")


# --- pl.v -------------------------------------------------------------------------------------------------------
def parity_script(root: Path, baselines: str) -> None:
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "verify_api_integration.py").write_text(f"BASELINES = {baselines}\n", encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R016.99")
def test_v_ports_baseline_and_deletes_script_and_test(repo: Path) -> None:
    parity_script(repo, '{"demo-mcp": 50.0, "other": 90.0}')
    (repo / "tests").mkdir()
    (repo / "tests" / "test_verify_api_integration.py").write_text("# verify_api_integration\n", encoding="utf-8")
    ctx = run(repo, "pl.v")
    assert toml(repo)["tool"]["pipelines"]["api_integration"] == {"baseline": 50.0}
    assert not (repo / "scripts" / "verify_api_integration.py").exists()
    assert not (repo / "tests" / "test_verify_api_integration.py").exists()
    assert not ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.99")
def test_v_stale_baseline_is_lowered_and_reviewed(repo: Path) -> None:
    parity_script(repo, '{"demo-mcp": 99.0}')
    ctx = run(repo, "pl.v")
    assert toml(repo)["tool"]["pipelines"]["api_integration"] == {"baseline": 50.0}
    assert any("below the ported baseline" in i["detail"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.99")
def test_v_missing_entry_means_no_table_and_unreadable_baselines_are_blocking(repo: Path) -> None:
    parity_script(repo, '{"other": 90.0}')
    run(repo, "pl.v")
    assert (
        "pipelines" not in toml(repo).get("tool", {}) and not (repo / "scripts" / "verify_api_integration.py").exists()
    )


@pytest.mark.spec("PIPE-GATES-R016.99")
def test_v_dynamic_baselines_table_is_blocking(repo: Path) -> None:
    (repo / "scripts").mkdir()
    (repo / "scripts" / "verify_api_integration.py").write_text("BASELINES = load()\n", encoding="utf-8")
    ctx = run(repo, "pl.v")
    assert blocking(ctx, "pl.v") and (repo / "scripts" / "verify_api_integration.py").exists()


# --- pl.s -------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.96")
def test_s_drops_dupehound_skip_and_bump2version_step(repo: Path) -> None:
    wf = repo / ".github/workflows/connector-pr.yml"
    wf.write_text(
        "jobs:\n  gates:\n    with:\n      skip-hooks: docker-compose-check,dupehound-changed\n"
        "  setup:\n    steps:\n      - name: Install\n        run: uv tool install bump2version\n      - run: echo ok\n",
        encoding="utf-8",
    )
    run(repo, "pl.s")
    text = wf.read_text()
    assert "skip-hooks: docker-compose-check\n" in text and "dupehound" not in text and "bump2version" not in text
    assert "echo ok" in text


@pytest.mark.spec("PIPE-GATES-R016.96")
def test_s_other_bump2version_shape_goes_to_review(repo: Path) -> None:
    wf = repo / ".github/workflows/connector-pr.yml"
    body = "jobs:\n  x:\n    steps:\n      - run: |\n          uv tool install bump2version\n          other\n"
    wf.write_text(body, encoding="utf-8")
    ctx = run(repo, "pl.s")
    assert wf.read_text() == body and ctx.review.items


# --- whole module ------------------------------------------------------------------------------------------------
def test_order_names_registered_rules() -> None:
    assert P.ORDER == ("pl.n", "pl.o", "pl.p", "pl.q", "pl.r", "pl.t", "pl.u", "pl.v", "pl.s")
    assert all(rid in RULES for rid in P.ORDER)


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_second_run_changes_nothing(repo: Path) -> None:
    old_docker(repo)
    ontology(repo)
    security_dir(repo)
    parity_script(repo, '{"demo-mcp": 50.0}')
    (repo / "scripts" / "bootstrap.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / ".bumpversion.cfg").write_text("[bumpversion]\ncurrent_version = 1.2.3\n", encoding="utf-8")
    (repo / ".codespellignore").write_text("zzword\n", encoding="utf-8")
    (repo / ".pre-commit-config.yaml").write_text(OLD_HOOKS, encoding="utf-8")
    run(repo, *P.ORDER)
    after_first = snapshot(repo)
    second = run(repo, *P.ORDER)
    assert snapshot(repo) == after_first
    assert not second.changed and not second.deleted
    assert re.search(r"connector: true", (repo / ".github/workflows/pipeline.yml").read_text())


# --- pl.x -------------------------------------------------------------------------------------------------------
ROW_X = "PIPE-GATES-R016.102"


def extras(root: Path, *names: str) -> None:
    for name in names:
        (root / name).write_text("x\n", encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R016.102")
def test_x_row_and_order() -> None:
    from pipelines_hooks.hygiene.connector_central import base, rule_order, scaffold

    assert base.RULE_ROWS["pl.x"] == ROW_X and scaffold.ORDER == ("pl.x",)
    assert rule_order()[-1] == "pl.x"


@pytest.mark.spec("PIPE-GATES-R016.102")
def test_x_deletes_unreferenced_files(repo: Path) -> None:
    names = ("MANIFEST.in", "requirements.txt", ".dockerignore", ".env.example", "mcp_config.json", "opencode.json")
    extras(repo, *names)
    ctx = run(repo, "pl.x")
    assert ctx.deleted == set(names)
    assert not any((repo / n).exists() for n in names) and not ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.102")
def test_x_referenced_file_stays_with_a_review_item_naming_the_referrers(repo: Path) -> None:
    extras(repo, "requirements.txt", "opencode.json")
    (repo / "README.md").write_text("Install with `pip install -r requirements.txt`.\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("opencode.json was added\n", encoding="utf-8")
    (repo / "uv.lock").write_text("requirements.txt\n", encoding="utf-8")
    ctx = run(repo, "pl.x")
    assert (repo / "requirements.txt").exists() and not (repo / "opencode.json").exists()
    [item] = ctx.review.items
    assert item["step"] == "pl.x" and not item["blocking"] and "README.md" in item["detail"]
    assert item["path"] == "requirements.txt"


@pytest.mark.spec("PIPE-GATES-R016.102")
def test_x_match_is_a_whole_name(repo: Path) -> None:
    extras(repo, "requirements.txt")
    (repo / "README.md").write_text("see dev-requirements.txt and requirements.txt.bak\n", encoding="utf-8")
    ctx = run(repo, "pl.x")
    assert ctx.deleted == {"requirements.txt"}
    (repo / "requirements.txt").write_text("x\n", encoding="utf-8")
    (repo / "README.md").write_text("see docs/requirements.txt.\n", encoding="utf-8")
    assert run(repo, "pl.x").review.items


@pytest.mark.spec("PIPE-GATES-R016.102")
def test_x_dockerignore_stays_while_a_dockerfile_exists(repo: Path) -> None:
    extras(repo, ".dockerignore")
    (repo / "docker").mkdir()
    (repo / "docker" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    ctx = run(repo, "pl.x")
    assert (repo / ".dockerignore").exists() and "docker/Dockerfile" in ctx.review.items[0]["detail"]
    (repo / "docker" / "Dockerfile").unlink()
    assert run(repo, "pl.x").deleted == {".dockerignore"}


@pytest.mark.spec("PIPE-GATES-R016.102")
def test_x_dockerignore_goes_after_pl_o_removes_the_dockerfile(repo: Path) -> None:
    old_docker(repo)
    extras(repo, ".dockerignore")
    ctx = run(repo, "pl.o", "pl.x")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert ".dockerignore" in ctx.deleted


@pytest.mark.spec("PIPE-GATES-R016.102")
def test_x_mcp_config_is_referenced_by_package_data_and_manifest_globs(repo: Path) -> None:
    extras(repo, "mcp_config.json")
    (repo / "pyproject.toml").write_text(PYPROJECT + "\n[tool.setuptools.package-data]\n", encoding="utf-8")
    base = PYPROJECT.replace('demo_mcp = ["ontology/**"]', 'demo_mcp = ["ontology/**"]\n"" = ["mcp_config.json"]')
    (repo / "pyproject.toml").write_text(base, encoding="utf-8")
    ctx = run(repo, "pl.x")
    assert (repo / "mcp_config.json").exists() and "pyproject.toml" in ctx.review.items[0]["detail"]
    (repo / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    extras(repo, "MANIFEST.in")
    (repo / "MANIFEST.in").write_text("include *.json\n", encoding="utf-8")
    ctx = run(repo, "pl.x")
    # MANIFEST.in itself is unreferenced and goes first, so its glob stops counting
    assert ctx.deleted == {"MANIFEST.in", "mcp_config.json"} and not ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.102")
def test_x_second_run_changes_nothing(repo: Path) -> None:
    extras(repo, "requirements.txt", "opencode.json", ".env.example")
    (repo / "README.md").write_text("uses .env.example\n", encoding="utf-8")
    run(repo, "pl.x")
    after = snapshot(repo)
    second = run(repo, "pl.x")
    assert snapshot(repo) == after and not second.deleted and not second.changed
