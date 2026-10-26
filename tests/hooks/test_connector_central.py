"""Connector release and config boilerplate owned by pipelines (PIPE-RELEASE-R001.13-.15, PIPE-GATES-R008.1,
PIPE-GATES-R016.39-.40, PIPE-VALIDATION-R001.7-.9)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.cli import GATES, run_gate
from pipelines_hooks.connector import cli as connector_cli
from pipelines_hooks.connector import codespell, container, files, generate, version
from pipelines_hooks.core.errors import CannotRun
from tests.git_fixture_environment import fixture_git_environment

ROOT = Path(__file__).parents[2]
WORKFLOWS = ROOT / ".github/workflows"

PYPROJECT = """[project]
name = "demo-mcp"
version = "1.2.3"  # keep
[project.optional-dependencies]
mcp = []
agent = []
[project.scripts]
demo-mcp = "demo_mcp.mcp_server:main"
demo-agent = "demo_mcp.agent_server:main"
[project.entry-points."agent_connector_sdk.connector"]
demo-mcp = "demo_mcp"
[tool.pipelines.container]
port = 9000
runtime_apt = ["ffmpeg"]
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], env=fixture_git_environment(), check=True, capture_output=True)


def _repo(tmp_path: Path, pyproject: str = PYPROJECT) -> Path:
    root = tmp_path / "demo-mcp"
    (root / "demo_mcp" / "ontology" / "mappings").mkdir(parents=True)
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (root / "demo_mcp" / "ontology" / "mappings" / "source.yaml").write_text(
        "ontology_source: media\n", encoding="utf-8"
    )
    (root / "demo_mcp" / "ontology" / "media.ttl").write_text(
        ':Book a owl:Class ;\n    rdfs:label "Book" .\n:Author a owl:Class .\n', encoding="utf-8"
    )
    (root / "connector_manifest.yml").write_text("connector: demo-mcp\n", encoding="utf-8")
    _git(root, "init", "-q")
    return root


def _commit_all(root: Path, *names: str) -> None:
    _git(root, "add", "--", *names)


# --- PIPE-RELEASE-R001.13: version and container files ---------------------------------------------------------
@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_bump_changes_pyproject_only_and_keeps_the_comment(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "README.md").write_text("Version: 1.2.3\n", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert version.main(["--root", str(root), "bump", "patch"]) == 0
    after = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert [n for n in after if after[n] != before[n]] == ["pyproject.toml"]
    assert 'version = "1.2.4"  # keep' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert version.bumped("1.2.9", "minor") == "1.3.0" and version.bumped("1.2.9", "major") == "2.0.0"
    with pytest.raises(CannotRun):
        version.bumped("1.2", "patch")


@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_version_bump_ignores_other_tables(tmp_path: Path) -> None:
    root = _repo(tmp_path, '[tool.x]\nversion = "9.9.9"\n' + PYPROJECT)
    assert version.read_version(root) == "1.2.3"
    version.write_version(root, "1.2.4")
    assert 'version = "9.9.9"' in (root / "pyproject.toml").read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_render_is_deterministic_and_driven_by_the_table(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    first, second = container.render(root), container.render(root)
    assert first == second and set(first) == {"Dockerfile", "debug.Dockerfile", "mcp.compose.yml", "agent.compose.yml"}
    docker = first["Dockerfile"]
    assert "demo-mcp[mcp]==1.2.3" in docker and "demo-mcp[agent]==1.2.3" in docker
    assert "ARG PORT=9000" in docker and "ffmpeg" in docker and "ARG SDK_VERSION=" in docker
    assert "--upgrade-package agent-connector-sdk" in docker and "COPY . " not in docker
    assert 'CMD ["demo-mcp"]' in docker and 'CMD ["demo-agent"]' in docker
    assert "@@" not in "".join(first.values())
    assert 'CMD ["demo-mcp"]' in first["debug.Dockerfile"] and "COPY . /app" in first["debug.Dockerfile"]
    compose = yaml.safe_load(first["mcp.compose.yml"])["services"]["demo-mcp-mcp"]
    assert compose["ports"] == [{"host_ip": "127.0.0.1", "published": "9000", "target": 9000}]
    assert compose["user"] == "10001:10001"
    version.write_version(root, "1.2.4")
    assert "demo-mcp[mcp]==1.2.4" in container.render(root)["Dockerfile"]


@pytest.mark.spec("PIPE-RELEASE-R010")
def test_render_applies_named_source_build_allowance_to_each_runtime_target(tmp_path: Path) -> None:
    pyproject = PYPROJECT.replace(
        "[tool.pipelines.container]",
        '[tool.pipelines]\nallow-source-build = ["Uptime_Kuma.API", "pyspark"]\n\n[tool.pipelines.container]',
        1,
    )
    docker = container.render(_repo(tmp_path, pyproject))["Dockerfile"]
    install = "--only-binary :all: --no-binary pyspark --no-binary uptime-kuma-api"
    assert docker.count(install) == 2
    assert "demo-mcp[mcp]==1.2.3" in docker and "demo-mcp[agent]==1.2.3" in docker
    assert "--no-binary demo-mcp" not in docker


@pytest.mark.spec("PIPE-RELEASE-R010")
@pytest.mark.parametrize("allowance", ['[":all:"]', '["a", "A"]', '["bad name"]'])
def test_render_refuses_invalid_named_source_build_allowance(tmp_path: Path, allowance: str) -> None:
    pyproject = PYPROJECT.replace(
        "[tool.pipelines.container]",
        f"[tool.pipelines]\nallow-source-build = {allowance}\n\n[tool.pipelines.container]",
        1,
    )
    with pytest.raises(CannotRun):
        container.render(_repo(tmp_path, pyproject))


@pytest.mark.spec("PIPE-RELEASE-R010")
def test_render_refuses_the_published_package_as_a_source_build(tmp_path: Path) -> None:
    pyproject = PYPROJECT.replace(
        "[tool.pipelines.container]",
        '[tool.pipelines]\nallow-source-build = ["demo_mcp"]\n\n[tool.pipelines.container]',
        1,
    )
    with pytest.raises(CannotRun, match="published package itself"):
        container.render(_repo(tmp_path, pyproject))


@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_render_preserves_explicit_runtime_contract(tmp_path: Path) -> None:
    pyproject = (
        PYPROJECT
        + """
image_var = "SYSTEMS_MANAGER_MCP_IMAGE_DIGEST"
restart = "unless-stopped"
tmpfs_size = "128m"
env_file_mode = "none"
compose_host = {env = "SYSTEMS_MANAGER_MCP_BIND_ADDRESS", default = "127.0.0.1"}
publish_port = {env = "SYSTEMS_MANAGER_MCP_PORT", default = 9000}
container_name = false
hostname = false
health_timeout = "5s"
health_command_timeout = 3
compose_env = ["AUTH_TYPE=${AUTH_TYPE:?authenticated MCP transport required}"]
limits = {mcp = {memory_limit_env = "", memory_limit = "1g", cpu_limit_env = "", cpu_limit = "1.0"}}
"""
    )
    root = _repo(tmp_path, pyproject)
    compose = container.render(root)["mcp.compose.yml"]
    assert (
        "image: ${SYSTEMS_MANAGER_MCP_IMAGE_DIGEST:?set-SYSTEMS_MANAGER_MCP_IMAGE_DIGEST-to-image@sha256-digest}"
        in compose
    )
    assert "restart: unless-stopped\n" in compose and "size=128m\n" in compose
    assert "mem_limit: 1g\n    cpus: 1.0\n" in compose
    assert "    env_file:" not in compose
    assert "- AUTH_TYPE=${AUTH_TYPE:?authenticated MCP transport required}\n" in compose
    assert 'host_ip: "${SYSTEMS_MANAGER_MCP_BIND_ADDRESS:-127.0.0.1}"' in compose
    assert 'published: "${SYSTEMS_MANAGER_MCP_PORT:-9000}"' in compose
    assert "target: 9000" in compose
    assert "container_name:" not in compose and "hostname:" not in compose
    assert '    init: true\n    user: "10001:10001"\n    read_only: true\n' in compose
    assert (
        "    cap_drop:\n      - ALL\n    security_opt:\n      - no-new-privileges:true\n    pids_limit: 256\n"
        in compose
    )
    assert "urlopen('http://localhost:9000/health', timeout=3)" in compose
    assert "      timeout: 5s\n" in compose


@pytest.mark.spec("PIPE-RELEASE-R001.13")
@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("0.0.0.0", "0.0.0.0"),
        ("::1", "::1"),
    ],
)
def test_render_uses_a_validated_compose_host(tmp_path: Path, host: str, expected: str) -> None:
    pyproject = PYPROJECT.replace("port = 9000\n", f'port = 9000\ncompose_host = "{host}"\n')
    root = _repo(tmp_path, pyproject)
    compose = yaml.safe_load(container.render(root)["mcp.compose.yml"])["services"]["demo-mcp-mcp"]
    assert compose["ports"] == [{"host_ip": expected, "published": "9000", "target": 9000}]


@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_render_resolves_typed_bindings_through_compose(tmp_path: Path) -> None:
    pyproject = PYPROJECT.replace(
        "port = 9000\n",
        'port = 9000\ncompose_host = {env = "DEMO_BIND", default = "127.0.0.1"}\n'
        'publish_port = {env = "DEMO_PORT", default = 9000}\nenv_file_mode = "none"\n',
    )
    root = _repo(tmp_path, pyproject)
    compose_path = tmp_path / "compose.yml"
    compose_path.write_text(container.render(root)["mcp.compose.yml"], encoding="utf-8")
    base_env = {"DEMO_MCP_MCP_IMAGE": "example.invalid/demo@sha256:" + "a" * 64}
    for bind in ("127.0.0.1", "::1"):
        env = {**base_env, "DEMO_BIND": bind, "DEMO_PORT": "9001"}
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "config", "--quiet"],
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    for bind in ("localhost", "127.0.0.1:9000", "[::1]", "fe80::1%eth0"):
        env = {**base_env, "DEMO_BIND": bind, "DEMO_PORT": "9001"}
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "config", "--quiet"],
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, bind


@pytest.mark.spec("PIPE-RELEASE-R001.13")
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("image_var", "not-an-env-name"),
        ("restart", "sometimes"),
        ("tmpfs_size", "0m"),
        ("publish_port", "9000:9001"),
        ("health_timeout", "0s"),
        ("health_command_timeout", 0),
        ("env_file_mode", "secret"),
    ],
)
def test_render_refuses_invalid_runtime_contract(tmp_path: Path, key: str, value: object) -> None:
    rendered = json.dumps(value) if isinstance(value, str) else str(value).lower()
    root = _repo(tmp_path, PYPROJECT + f"{key} = {rendered}\n")
    with pytest.raises(CannotRun):
        container.render(root)


@pytest.mark.spec("PIPE-RELEASE-R001.13")
@pytest.mark.parametrize(
    "host",
    [
        "",
        " 127.0.0.1",
        "127.0.0.1:9000",
        "127.0.0.999",
        "http://127.0.0.1",
        "127.0.0.1/24",
        "[::1]",
        "fe80::1%eth0",
        "localhost",
        "connector.example",
        "bad host",
        "*",
        "a..b",
        "-connector.example",
    ],
)
def test_render_refuses_an_invalid_compose_host(tmp_path: Path, host: str) -> None:
    pyproject = PYPROJECT.replace("port = 9000\n", f'port = 9000\ncompose_host = "{host}"\n')
    with pytest.raises(CannotRun, match="compose_host"):
        container.render(_repo(tmp_path, pyproject))


@pytest.mark.spec("PIPE-RELEASE-R001.13")
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("compose_host", '{env = "bad-name", default = "127.0.0.1"}'),
        ("compose_host", '{env = "GOOD", default = "127.0.0.1:9000"}'),
        ("compose_host", '{env = "GOOD", default = "127.0.0.1", extra = "refuse"}'),
        ("publish_port", '{env = "GOOD", default = 0}'),
        ("publish_port", '{env = "GOOD", default = "9000:9001"}'),
        ("publish_port", '{env = "GOOD", default = 9000, extra = "refuse"}'),
    ],
)
def test_render_refuses_malformed_typed_bindings(tmp_path: Path, key: str, value: str) -> None:
    with pytest.raises(CannotRun, match=key.split("_")[0]):
        container.render(_repo(tmp_path, PYPROJECT + f"{key} = {value}\n"))


@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_render_refuses_the_retired_publish_host_alias(tmp_path: Path) -> None:
    with pytest.raises(CannotRun, match="unknown keys.*publish_host"):
        container.render(_repo(tmp_path, PYPROJECT + 'publish_host = "127.0.0.1"\n'))


@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_render_refreshes_the_detected_branded_sdk_distribution(tmp_path: Path) -> None:
    pyproject = PYPROJECT.replace(
        "[project.optional-dependencies]", 'dependencies = ["scion-sdk[mcp]>=1.0"]\n[project.optional-dependencies]'
    )
    docker = container.render(_repo(tmp_path, pyproject))["Dockerfile"]
    assert "--upgrade-package scion-sdk" in docker
    assert "--upgrade-package agent-connector-sdk" not in docker


@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_render_refuses_an_unknown_table_key_and_a_missing_entrypoint(tmp_path: Path) -> None:
    with pytest.raises(CannotRun, match="unknown keys"):
        container.render(_repo(tmp_path, PYPROJECT + "bogus = 1\n"))
    bare = PYPROJECT.replace('demo-mcp = "demo_mcp.mcp_server:main"\ndemo-agent = "demo_mcp.agent_server:main"\n', "")
    with pytest.raises(CannotRun, match="entrypoint"):
        container.render(_repo(tmp_path / "b", bare))


@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_render_writes_files_and_check_fails_on_a_committed_rendering(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    out = tmp_path / "out"
    assert container.main(["--root", str(root), "--out", str(out)]) == 0
    assert (out / "Dockerfile").read_text(encoding="utf-8") == container.render(root)["Dockerfile"]
    assert container.main(["--root", str(root), "--check"]) == 0
    (root / "docker").mkdir()
    (root / "docker" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    _commit_all(root, "docker/Dockerfile")
    assert container.main(["--root", str(root), "--check"]) == 1


@pytest.mark.spec("PIPE-RELEASE-R001.14")
def test_container_workflow_renders_and_tags_by_sdk_version() -> None:
    document = yaml.safe_load((WORKFLOWS / "container_pipeline.yml").read_text(encoding="utf-8"))
    inputs = document[True]["workflow_call"]["inputs"]
    assert inputs["render_connector"]["default"] is False and inputs["sdk_version"]["default"] == ""
    assert inputs["legacy_profile"]["default"] is False and inputs["legacy_profile"]["type"] == "boolean"
    steps = document["jobs"]["publish-docker"]["steps"]
    render_needed = next(s for s in steps if s.get("id") == "render-needed")
    assert "agent_connector_sdk.connector" in render_needed["run"]
    render = next(s for s in steps if s.get("id") == "render")
    assert "pipelines-connector render" in render["run"]
    assert render["if"] == "steps.render-needed.outputs.render == 'true'"
    meta = next(s for s in steps if s.get("id") == "meta")
    assert "-sdk${{ inputs.sdk_version }}" in meta["with"]["tags"]
    assert "-sdk-${{ inputs.sdk_distribution }}-${{ inputs.sdk_version }}" in meta["with"]["tags"]
    assert "inputs.sdk_distribution == 'scion-sdk'" in meta["with"]["tags"]


@pytest.mark.spec("PIPE-RELEASE-R001.14")
def test_sdk_rebuild_workflow_skips_a_built_tag_and_rebuilds_through_the_container_pipeline() -> None:
    document = yaml.safe_load((WORKFLOWS / "connector_sdk_rebuild_pipeline.yml").read_text(encoding="utf-8"))
    resolve, rebuild = document["jobs"]["resolve"], document["jobs"]["rebuild"]
    inputs = document[True]["workflow_call"]["inputs"]
    assert inputs["release_repair"]["type"] == "boolean" and inputs["release_repair"]["default"] is False
    assert inputs["legacy_profile"]["type"] == "boolean" and inputs["legacy_profile"]["default"] is False
    assert inputs["release_source_sha"]["type"] == "string" and inputs["release_source_sha"]["default"] == ""
    assert inputs["release_source_epoch"]["type"] == "string" and inputs["release_source_epoch"]["default"] == ""
    login = next(step for step in resolve["steps"] if "docker/login-action@" in step.get("uses", ""))
    assert login["if"] == "inputs.release_repair != true"
    source = next(step for step in resolve["steps"] if step.get("name") == "Checkout immutable release source")
    assert source["if"] == "inputs.release_repair == true"
    assert source["with"]["ref"] == "${{ inputs.release_source_sha }}"
    assert source["with"]["fetch-depth"] == 0
    script = next(s for s in resolve["steps"] if s.get("id") == "sdk")["run"]
    assert "imagetools inspect" in script and "-sdk${sdk}" in script and "pypi.org/pypi/" in script
    assert "sdk_distribution" in script and "scion-sdk" in script
    assert "PAYLOAD_SDK_DISTRIBUTION" in script and "INPUT_SDK_DISTRIBUTION:-${PAYLOAD_SDK_DISTRIBUTION:-}" in script
    assert 'sdk_tag="${version}-sdk-${sdk_distribution}-${sdk}"' in script
    assert 'RELEASE_REPAIR,,}" != true' in script
    assert rebuild["needs"] == "resolve" and rebuild["if"] == "needs.resolve.outputs.stale == 'true'"
    assert rebuild["uses"].endswith("/container_pipeline.yml@main")
    assert rebuild["with"] == {
        "render_connector": "${{ !inputs.legacy_profile }}",
        "legacy_profile": "${{ inputs.legacy_profile }}",
        "release_repair": "${{ inputs.release_repair }}",
        "release_source_sha": "${{ inputs.release_source_sha }}",
        "release_source_epoch": "${{ inputs.release_source_epoch }}",
        "sdk_version": "${{ needs.resolve.outputs.sdk_version }}",
        "sdk_distribution": "${{ needs.resolve.outputs.sdk_distribution }}",
    }


# --- generated ontology artifacts ------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.39")
def test_generate_is_deterministic_and_derives_shapes_from_declared_classes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    root = _repo(tmp_path)
    assert generate.main(["--root", str(root)]) == 0
    shapes = root / "demo_mcp/ontology/shapes/connector.shacl.ttl"
    cert = root / "demo_mcp/ontology/certification.json"
    first = (shapes.read_bytes(), cert.read_bytes())
    assert generate.main(["--root", str(root)]) == 0 and first == (shapes.read_bytes(), cert.read_bytes())
    text = shapes.read_text(encoding="utf-8")
    assert "shape:AuthorGovernanceShape a sh:NodeShape" in text and "shape:BookGovernanceShape" in text
    assert text.index("AuthorGovernance") < text.index("BookGovernance")
    assert "<http://knuckles.team/kg/media/shape#>" in text and text.count("sh:path :provenanceReference") == 2
    record = json.loads(cert.read_text(encoding="utf-8"))
    assert record["validated_at"] == "2023-11-14T22:13:20Z" and record["connector"] == "demo-mcp"
    digest = hashlib.sha256(shapes.read_bytes()).hexdigest()
    assert record["artifacts"]["demo_mcp/ontology/shapes/connector.shacl.ttl"] == digest
    assert "connector_manifest.yml" in record["artifacts"] and record["signature"] is None


@pytest.mark.spec("PIPE-GATES-R016.39")
def test_generate_honours_the_shape_classes_override_and_refuses_a_missing_source(tmp_path: Path) -> None:
    root = _repo(tmp_path, PYPROJECT + '[tool.pipelines.ontology]\nshape_classes = ["Zed"]\n')
    generate.main(["--root", str(root)])
    text = (root / "demo_mcp/ontology/shapes/connector.shacl.ttl").read_text(encoding="utf-8")
    assert "ZedGovernanceShape" in text and "BookGovernanceShape" not in text
    (root / "demo_mcp/ontology/mappings/source.yaml").unlink()
    with pytest.raises(CannotRun):
        generate.generate(root)


@pytest.mark.spec("PIPE-GATES-R016.39")
def test_python_release_workflow_generates_before_the_build() -> None:
    document = yaml.safe_load((WORKFLOWS / "python_pipeline.yml").read_text(encoding="utf-8"))
    assert document[True]["workflow_call"]["inputs"]["connector"]["default"] is False
    steps = [s["name"] for s in next(iter(document["jobs"].values()))["steps"]]
    assert steps.index("Generate the connector ontology artifacts") < steps.index("Build, publish and release")


# --- standard files are provided, not committed ----------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R008.1")
def test_a_hardcoded_package_version_is_a_finding_and_metadata_is_not(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "demo_mcp/__init__.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    _commit_all(root, "demo_mcp/__init__.py")
    assert any("spells the package version" in f for f in files.findings(root))
    (root / "demo_mcp/__init__.py").write_text(
        "from importlib.metadata import version\n__version__ = version('demo-mcp')\n", encoding="utf-8"
    )
    assert files.findings(root) == []


@pytest.mark.spec("PIPE-VALIDATION-R001.7")
def test_committed_copies_of_central_files_fail_and_a_clean_repo_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert files.main(["--root", str(root)]) == 0
    planted = {
        "scripts/security_sanitizer.py": "x\n",
        ".bumpversion.cfg": "[bumpversion]\n",
        "docker/Dockerfile": "FROM scratch\n",
        "demo_mcp/ontology/certification.json": "{}\n",
        "demo_mcp/ontology/shapes/connector.shacl.ttl": "\n",
    }
    for name, text in planted.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    _commit_all(root, *planted)
    found = files.findings(root)
    assert len(found) == len(planted) and files.main(["--root", str(root)]) == 1


@pytest.mark.spec("PIPE-VALIDATION-R001.7")
def test_connector_standard_is_a_group_and_a_published_hook() -> None:
    assert GATES["connector-standard"] == "pipelines_hooks.connector.standard"
    hooks = {h["id"]: h for h in yaml.safe_load((ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))}
    assert hooks["connector-standard"]["entry"] == "pipelines-hook connector-standard"
    assert "codespell==2.4.2" in hooks["connector-standard"]["additional_dependencies"]


@pytest.mark.spec("PIPE-VALIDATION-R001.8")
def test_codespell_defaults_are_shared_and_extended_from_pyproject(tmp_path: Path) -> None:
    root = _repo(tmp_path, PYPROJECT + '[tool.pipelines.codespell]\nignore_words = ["zorp"]\n')
    words = codespell.ignore_words(root)
    assert "zorp" in words and "linar" in words and words == sorted(set(words))
    (root / "README.md").write_text("A fine readme with a wrold typo.\n", encoding="utf-8")
    _commit_all(root, "README.md")
    status = run_gate("connector-standard", ["--root", str(root)])
    assert status in (1, 2)  # 1 when codespell runs here, 2 fail-closed without it under CI


@pytest.mark.spec("PIPE-VALIDATION-R001.9")
def test_reference_connector_config_names_only_published_hooks() -> None:
    config = yaml.safe_load((ROOT / "templates/connector/pre-commit-config.yaml").read_text(encoding="utf-8"))
    ours = next(r for r in config["repos"] if r["repo"].endswith("/pipelines"))
    assert ours["rev"] == "main"
    published = {h["id"] for h in yaml.safe_load((ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))}
    ids = {h["id"] for h in ours["hooks"]}
    assert ids <= published and {"connector-standard", "secrets", "dependency-readiness"} <= ids
    assert not any(h["id"] in {"security-sanitizer", "check-bumpversion"} for r in config["repos"] for h in r["hooks"])
    assert len(yaml.safe_dump(config).splitlines()) < 60


# --- dupehound on pull requests --------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.40")
def test_connector_pr_workflow_builds_the_pinned_dupehound_instead_of_skipping_it() -> None:
    pr = yaml.safe_load((WORKFLOWS / "connector_pr_pipeline.yml").read_text(encoding="utf-8"))
    assert pr["jobs"]["gates"]["with"]["scanners"] == "dupehound"
    assert "dupehound" not in pr[True]["workflow_call"]["inputs"]["skip-hooks"]["default"]
    gates = yaml.safe_load((WORKFLOWS / "gates_pipeline.yml").read_text(encoding="utf-8"))
    assert gates[True]["workflow_call"]["inputs"]["scanners"]["default"] == ""
    steps = gates["jobs"]["gates"]["steps"]
    names = [s.get("name") for s in steps]
    build = names.index("Build the pinned scanners and put them on PATH")
    assert build < names.index("pre-commit (commit and pre-push stages)")
    assert 'install_scanners.sh" "$ROOT" $SCANNERS' in steps[build]["run"]


@pytest.mark.spec("PIPE-GATES-R016.42")
def test_connector_pr_workflow_installs_the_identity_catalog_from_the_callers_variable_and_stays_fail_closed() -> None:
    pr = yaml.safe_load((WORKFLOWS / "connector_pr_pipeline.yml").read_text(encoding="utf-8"))
    setup = pr["jobs"]["gates"]["with"]["setup-command"]
    assert "printf '%s' \"$PROHIBITED_IDENTITY_CATALOG\"" in setup and "prohibited-identities.json" in setup
    assert setup.index("PROHIBITED_IDENTITY_CATALOG") < setup.index("uv sync")
    gates = yaml.safe_load((WORKFLOWS / "gates_pipeline.yml").read_text(encoding="utf-8"))
    step = next(s for s in gates["jobs"]["gates"]["steps"] if s.get("name") == "Caller setup")
    assert step["env"]["PROHIBITED_IDENTITY_CATALOG"] == "${{ vars.PROHIBITED_IDENTITY_CATALOG }}"
    assert (
        "tracked-privacy" not in pr["jobs"]["gates"]["with"]["skip-hooks"]
        and "secrets" not in pr[True]["workflow_call"]["inputs"]["skip-hooks"]["default"]
    )


@pytest.mark.spec("PIPE-GATES-R016.40")
def test_scanner_installer_installs_only_the_named_scanners(tmp_path: Path) -> None:
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "cargo").write_text(
        '#!/usr/bin/env bash\nroot=""\nwhile [[ $# -gt 0 ]]; do [[ "$1" == --root ]] && root="$2"; shift; done\nmkdir -p "$root/bin"; : > "$root/bin/$(basename "$root")"; chmod +x "$root/bin/$(basename "$root")"\n',
        encoding="utf-8",
    )
    (fake / "cargo").chmod(0o755)
    root = tmp_path / "scanners"
    done = subprocess.run(
        ["bash", str(ROOT / "scripts/install_scanners.sh"), str(root), "dupehound"],
        env={"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.split() == [str(root / "dupehound/bin")]
    assert (root / "dupehound/bin/dupehound").exists() and not (root / "cccc").exists() and not (root / "kiss").exists()


@pytest.mark.spec("PIPE-RELEASE-R001.13")
def test_pipelines_connector_command_dispatches_and_refuses_unknown(tmp_path: Path, capsys) -> None:
    root = _repo(tmp_path)
    assert connector_cli.main(["version", "--root", str(root), "read"]) == 0
    assert capsys.readouterr().out.strip() == "1.2.3"
    assert connector_cli.main(["nope"]) == 2
    assert connector_cli.main(["render", "--root", str(tmp_path / "missing")]) == 2
