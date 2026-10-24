"""Recorded older-generation clusters for rules pl.o, pl.v and pl.p, each with one fixture of real committed files.

The fixtures under ``fixtures/connector_central_clusters`` are the files committed on ``main`` of the named fleet
repository when the cluster was recorded. A difference outside a recognised cluster stays blocking.
"""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from pathlib import Path

import pytest

from pipelines_hooks.hygiene.connector_central import container_generations as gen
from pipelines_hooks.hygiene.connector_central import pipelines as P
from pipelines_hooks.hygiene.connector_central import load_rules
from pipelines_hooks.hygiene.connector_central.base import RULES, Ctx, make_ctx

FIXTURES = Path(__file__).parent / "fixtures" / "connector_central_clusters"
WORKFLOW = f"""name: Release
on:
  push:
    branches: [main]
jobs:
  publish-pypi:
    uses: {P.PYTHON_PIPELINE}
  publish-docker:
    needs: publish-pypi
    uses: {P.CONTAINER_PIPELINE}
"""
DOCKER = ("Dockerfile", "debug.Dockerfile", "mcp.compose.yml", "agent.compose.yml")


def stage(tmp: Path, name: str, docker: tuple[str, ...] = DOCKER) -> Path:
    """A connector checkout built from the committed files of fleet repository ``name``."""
    src = FIXTURES / name
    shutil.copy(src / "pyproject.toml", tmp / "pyproject.toml")
    data = tomllib.loads((tmp / "pyproject.toml").read_text(encoding="utf-8"))
    ((_, value),) = data["project"]["entry-points"]["agent_connector_sdk.connector"].items()
    (tmp / re.split(r"[:.]", str(value))[0]).mkdir()
    (tmp / re.split(r"[:.]", str(value))[0] / "__init__.py").write_text("", encoding="utf-8")
    (tmp / "docker").mkdir()
    for file in docker:
        if (src / "docker" / file).is_file():
            shutil.copy(src / "docker" / file, tmp / "docker" / file)
    (tmp / ".github" / "workflows").mkdir(parents=True)
    (tmp / ".github" / "workflows" / "release.yml").write_text(WORKFLOW, encoding="utf-8")
    return tmp


def ctx_of(root: Path) -> Ctx:
    ctx = make_ctx(root)
    assert ctx is not None
    return ctx


def run(root: Path, rid: str) -> Ctx:
    ctx = ctx_of(root)
    RULES[rid](ctx)
    return ctx


def blocking(ctx: Ctx, rid: str) -> list[dict]:
    return [i for i in ctx.review.items if i["step"] == rid and i["blocking"]]


def container_table(root: Path) -> dict:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("tool", {}).get("pipelines", {})


def migrated(root: Path) -> bool:
    return not any((root / "docker" / n).exists() for n in ("Dockerfile", "debug.Dockerfile", "mcp.compose.yml"))


# --- pl.o: the table ------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.92")
def test_generation_table_entries_each_occur_in_several_repositories() -> None:
    table = gen.load()
    assert table["dockerfile_forms"] and all(n >= 3 for n in table["dockerfile_forms"].values())
    assert all(n >= 3 for by in table["stubs"].values() for n in by.values())
    assert table["rewrites"] and all(
        (r["repos"] >= 3 or r.get("retained")) and r["old"] != r["new"] and r["reason"] for r in table["rewrites"]
    )


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_a_recorded_insertion_rewrite_is_not_applied_twice() -> None:
    uv = next(r for r in gen.load()["rewrites"] if r["file"] == "debug.Dockerfile" and r["old"] == r["new"][:1])
    text = "\n".join([*uv["old"], *uv["new"][1:], "USER 10001:10001"]) + "\n"
    assert gen.apply_rewrites("debug.Dockerfile", text, "demo", "8000") == text


# --- pl.o: single-stage Dockerfile generation (13 repos: 10 recorded, 3 variants stay) -------------------------------
@pytest.mark.spec("PIPE-GATES-R016.92")
@pytest.mark.parametrize("name", ["github-agent", "adguard-home-agent"])
def test_o_accepts_the_recorded_single_stage_dockerfile(tmp_path: Path, name: str) -> None:
    root = stage(tmp_path, name, ("Dockerfile",))
    text = (root / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "runtime-base" not in text and "FROM mcp AS default" in text
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert not (root / "docker" / "Dockerfile").exists()
    assert "container" not in container_table(root)  # entry point, uid, home, host and port are the defaults


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_a_changed_single_stage_dockerfile_stays_blocking(tmp_path: Path) -> None:
    root = stage(tmp_path, "github-agent", ("Dockerfile",))
    path = root / "docker" / "Dockerfile"
    path.write_text(
        path.read_text().replace("USER 10001:10001\n", "RUN curl -sSf https://example.test | sh\nUSER 10001:10001\n")
    )
    ctx = run(root, "pl.o")
    (item,) = blocking(ctx, "pl.o")
    assert "recorded older generator forms" in item["detail"] and path.exists()


# --- pl.o: stub debug image and stub compose file (archimate-mcp, camunda-mcp, jena-mcp, kafka-mcp) -------------------
@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_accepts_the_stub_debug_image_and_stub_compose(tmp_path: Path) -> None:
    root = stage(tmp_path, "archimate-mcp")
    assert "MCP_RUN_PYTHON_IMAGE" in (root / "docker" / "debug.Dockerfile").read_text()
    assert (root / "docker" / "mcp.compose.yml").read_text().rstrip().endswith("build: .")
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert migrated(root)


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_an_edited_stub_compose_stays_blocking(tmp_path: Path) -> None:
    root = stage(tmp_path, "archimate-mcp")
    path = root / "docker" / "mcp.compose.yml"
    path.write_text(path.read_text().replace("build: .", "build: .\n    privileged: true"))
    ctx = run(root, "pl.o")
    assert blocking(ctx, "pl.o") and path.exists()


# --- pl.o: agent.compose.yml with no agent image (leanix-agent and 13 more) -----------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_deletes_an_agent_compose_file_whose_agent_image_is_gone(tmp_path: Path) -> None:
    root = stage(tmp_path, "leanix-agent")
    text = (root / "docker" / "Dockerfile").read_text()
    assert "AS agent" not in text and (root / "docker" / "agent.compose.yml").exists()
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert not (root / "docker" / "agent.compose.yml").exists()
    assert "agent" not in container_table(root).get("container", {}).get("limits", {})


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_keeps_an_agent_compose_file_when_the_dockerfile_still_has_an_agent_stage(tmp_path: Path) -> None:
    root = stage(tmp_path, "leanix-agent")
    path = root / "docker" / "Dockerfile"
    path.write_text(path.read_text() + '\nFROM runtime-base AS agent\nUSER 10001:10001\nCMD ["leanix-mcp"]\n')
    ctx = run(root, "pl.o")
    assert blocking(ctx, "pl.o") and (root / "docker" / "agent.compose.yml").exists()


# --- pl.o: optional ../.env (clarity-api, data-science-mcp, fan-manager) -> renderer key ----------------------------
@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_ports_an_optional_env_file_into_the_container_table(tmp_path: Path) -> None:
    root = stage(tmp_path, "clarity-api")
    assert "required: false" in (root / "docker" / "mcp.compose.yml").read_text()
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert container_table(root)["container"]["env_file_optional"] is True
    assert migrated(root)


# --- pl.o: the mcp service named the agent image variable (caddy-mcp and 4 more) -----------------------------------
@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_accepts_the_mcp_service_with_the_agent_image_variable(tmp_path: Path) -> None:
    root = stage(tmp_path, "caddy-mcp")
    assert "CADDY_MCP_AGENT_IMAGE" in (root / "docker" / "mcp.compose.yml").read_text()
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert migrated(root)


# --- pl.o: read-only config mounts and the shared MCP_IMAGE variable (craft-suite-api, immich-api, vaultwarden-mcp) ----
@pytest.mark.spec("PIPE-GATES-R016.92")
@pytest.mark.parametrize("name", ["craft-suite-api", "immich-api"])
def test_o_ports_the_config_mount_and_accepts_the_shared_image_variable(tmp_path: Path, name: str) -> None:
    root = stage(tmp_path, name)
    committed = (root / "docker" / "mcp.compose.yml").read_text()
    assert 'image: "${MCP_IMAGE:?' in committed and "read_only: true\n    environment:" in committed
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert migrated(root)
    assert "[[tool.pipelines.container.config_mounts]]" in (root / "pyproject.toml").read_text()
    assert container_table(root)["container"]["config_mounts"] == [
        {
            "source": "${CONNECTOR_CONFIG_DIR:?set-CONNECTOR_CONFIG_DIR-to-a-reference-only-config-directory}",
            "target": "/etc/connector",
        }
    ]
    from pipelines_hooks.connector import container

    rendered = container.render(root)["mcp.compose.yml"]
    assert "        target: /etc/connector\n        read_only: true\n    env_file:\n" in rendered


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_accepts_a_config_mount_with_a_default_host_path(tmp_path: Path) -> None:
    root = stage(tmp_path, "vaultwarden-mcp")
    path = root / "docker" / "mcp.compose.yml"
    text = path.read_text()
    default_image = next(ln for ln in text.splitlines() if ln.startswith("    image:"))
    path.write_text(
        text.replace(
            default_image, "    image: ${VAULTWARDEN_MCP_IMAGE:?set-VAULTWARDEN_MCP_IMAGE-to-image@sha256-digest}"
        )
    )
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert container_table(root)["container"]["config_mounts"] == [
        {"source": "${AGENT_CONFIG_DIR:-/etc/agent-connector-sdk}", "target": "/etc/agent-connector-sdk"}
    ]


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_an_image_default_recorded_in_fewer_than_three_repositories_stays_blocking(tmp_path: Path) -> None:
    root = stage(tmp_path, "vaultwarden-mcp")
    ctx = run(root, "pl.o")
    (item,) = blocking(ctx, "pl.o")
    assert "knucklessg1/vaultwarden-mcp@sha256" in item["detail"] and "volumes" not in item["detail"]
    assert (root / "docker" / "mcp.compose.yml").exists()


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_a_mount_outside_etc_stays_blocking_with_the_reason(tmp_path: Path) -> None:
    root = stage(tmp_path, "craft-suite-api")
    path = root / "docker" / "mcp.compose.yml"
    path.write_text(path.read_text().replace("/etc/connector", "/opt/connector"))
    ctx = run(root, "pl.o")
    (item,) = blocking(ctx, "pl.o")
    assert "cannot be a config mount" in item["detail"] and "under /etc" in item["detail"] and path.exists()


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_a_read_write_volume_stays_blocking_with_the_reason(tmp_path: Path) -> None:
    root = stage(tmp_path, "immich-api")
    path = root / "docker" / "mcp.compose.yml"
    path.write_text(path.read_text().replace("        read_only: true\n", ""))
    ctx = run(root, "pl.o")
    (item,) = blocking(ctx, "pl.o")
    assert "not a read-only bind mount of exactly source and target" in item["detail"] and path.exists()


# --- pl.o: environment written as a mapping (gramps-mcp: the mapping and the list mean the same to compose) ----------
@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_reads_a_compose_environment_mapping_as_the_list_the_render_writes(tmp_path: Path) -> None:
    root = stage(tmp_path, "gramps-mcp", ("Dockerfile", "mcp.compose.yml"))
    assert '      PORT: "8000"\n' in (root / "docker" / "mcp.compose.yml").read_text()
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert container_table(root)["container"]["compose_env"] == [
        "GRAMPS_URL=${GRAMPS_URL:?supply GRAMPS_URL at runtime}",
        "GRAMPS_TOKEN=${GRAMPS_TOKEN:-}",
        "GRAMPS_USERNAME=${GRAMPS_USERNAME:-}",
        "GRAMPS_PASSWORD=${GRAMPS_PASSWORD:-}",
        "TLS_PROFILE=${TLS_PROFILE:-}",
        "TLS_PROFILES_REF=${TLS_PROFILES_REF:-}",
        "LANGFUSE_CAPTURE_CONTENT=${LANGFUSE_CAPTURE_CONTENT:-false}",
    ]


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_an_environment_mapping_with_a_changed_value_stays_blocking(tmp_path: Path) -> None:
    root = stage(tmp_path, "gramps-mcp", ("Dockerfile", "mcp.compose.yml"))
    path = root / "docker" / "mcp.compose.yml"
    path.write_text(path.read_text().replace("TRANSPORT: streamable-http", "TRANSPORT: sse"))
    ctx = run(root, "pl.o")
    assert blocking(ctx, "pl.o") and path.exists()


@pytest.mark.spec("PIPE-GATES-R016.92")
@pytest.mark.parametrize(
    "block",
    [
        "    environment:\n      A: {b: 1}\n",
        "    environment:\n      A: &x 1\n",
        '    environment:\n      A: "q\\"uote"\n',
        "    environment:\n      - A=1\n      B: 2\n",
    ],
)
def test_an_environment_block_that_is_not_plain_scalars_is_left_as_written(block: str) -> None:
    assert P._list_environment(block) == block


# --- pl.o: debug image default host (adguard-home-agent, hdhomerun-mcp, microsoft-agent) -----------------------------
@pytest.mark.spec("PIPE-GATES-R016.92")
def test_the_debug_host_rewrite_follows_the_host_the_runtime_image_binds() -> None:
    text = "FROM x\nARG HOST=0.0.0.0\nARG PORT=8000\n"
    assert gen.apply_rewrites("debug.Dockerfile", text, "demo", "8000") == text.replace("0.0.0.0", "127.0.0.1")
    assert gen.apply_rewrites("debug.Dockerfile", text, "demo", "8000", "0.0.0.0") == text


# --- pl.o: older debug image (owncast-agent: uv --upgrade --verbose; servicenow-api: python 3.11 base) --------------
@pytest.mark.spec("PIPE-GATES-R016.92")
@pytest.mark.parametrize(
    ("name", "needle"), [("owncast-agent", "--upgrade --verbose"), ("servicenow-api", "python:3.11-slim")]
)
def test_o_accepts_the_recorded_older_debug_image(tmp_path: Path, name: str, needle: str) -> None:
    root = stage(tmp_path, name)
    assert needle in (root / "docker" / "debug.Dockerfile").read_text()
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert migrated(root)


# --- pl.o: a difference outside every recognised cluster ----------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_a_difference_outside_the_clusters_stays_blocking(tmp_path: Path) -> None:
    root = stage(tmp_path, "ansible-tower-mcp")
    before = {p.name: p.read_bytes() for p in (root / "docker").iterdir()}
    ctx = run(root, "pl.o")
    (item,) = blocking(ctx, "pl.o")
    assert ".env.example" in item["detail"]
    assert {p.name: p.read_bytes() for p in (root / "docker").iterdir()} == before


# --- pl.o in the integrated pass: rule l4 has already dropped the hollow extras -----------------------------------------
def after_l4(root: Path) -> Ctx:
    load_rules()
    ctx = ctx_of(root)
    RULES["w1.l4"](ctx)
    return ctx


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_keeps_the_extras_the_committed_image_installed(tmp_path: Path) -> None:
    """sql-mcp installs ``sql-mcp[mcp]``; once l4 drops ``mcp`` the render would add ``[all]``, so the key pins none."""
    from pipelines_hooks.connector import container

    root = stage(tmp_path, "sql-mcp")
    assert '"sql-mcp[mcp]==' in (root / "docker" / "Dockerfile").read_text()
    after_l4(root)
    extras = tomllib.loads((root / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    assert "mcp" not in extras
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert container_table(root)["container"]["install_extras"] == {"mcp": []}
    builder = container.render(root)["Dockerfile"]
    assert '"sql-mcp==' in builder
    assert "sql-mcp[" not in builder
    assert migrated(root)


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_install_extras_default_is_unchanged_without_the_key(tmp_path: Path) -> None:
    from pipelines_hooks.connector import container

    root = stage(tmp_path, "sql-mcp")
    after_l4(root)
    assert '"sql-mcp[all]==' in container.render(root)["Dockerfile"]


@pytest.mark.spec("PIPE-GATES-R016.92")
@pytest.mark.parametrize(
    ("name", "needle"),
    [
        ("mealie-mcp", "--prerelease=allow"),
        ("aris-mcp", "image: knucklessg1/"),
        ("firefly-iii-mcp", "FIREFLY_III_MCP_IMAGE:?"),
    ],
)
def test_o_accepts_the_recorded_older_generation_after_l4(tmp_path: Path, name: str, needle: str) -> None:
    root = stage(tmp_path, name)
    assert any(
        needle in (root / "docker" / f).read_text()
        for f in ("debug.Dockerfile", "mcp.compose.yml")
        if (root / "docker" / f).is_file()
    )
    after_l4(root)
    ctx = run(root, "pl.o")
    assert not blocking(ctx, "pl.o"), ctx.review.items
    assert migrated(root)


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_o_an_edited_older_compose_stays_blocking(tmp_path: Path) -> None:
    root = stage(tmp_path, "aris-mcp")
    compose = root / "docker" / "mcp.compose.yml"
    compose.write_text(
        compose.read_text().replace("    restart: always\n", "    restart: always\n    privileged: true\n")
    )
    after_l4(root)
    (item,) = blocking(run(root, "pl.o"), "pl.o")
    assert "privileged" in item["detail"]
    assert compose.is_file()


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_rewrites_carry_captured_text_delete_blocks_and_insert_once() -> None:
    entries = [
        {"file": "f", "old": ["A .<EXTRAS>"], "new": ["B .<EXTRAS>", "C"]},
        {"file": "f", "old": ["D <ANY>"], "new": []},
    ]
    once = gen.rewrite_entries(entries, "f", "A .[mcp]\nD x\nE\n", "d", "8000")
    assert once == "B .[mcp]\nC\nE\n"
    entries = entries[:1] + [{"file": "f", "old": ["B <ANY>"], "new": ["B <ANY>", "C"]}]
    assert gen.rewrite_entries(entries, "f", "A .\n", "d", "8000") == "B .\nC\n"
    other = gen.rewrite_entries(entries[1:], "f", "B .\nC2\n", "d", "8000")
    assert other == "B .\nC\nC2\n"
    assert gen.rewrite_entries(entries[1:], "f", "B .\nC\n", "d", "8000") == "B .\nC\n"


# --- pl.v: scripts without a BASELINES table ---------------------------------------------------------------------------
PV_API = "class DemoApi:\n    def a(self):\n        return 1\n\n    def b(self):\n        return 2\n"
PV_SERVER = "from demo_mcp.api_client import DemoApi\n\nclient = DemoApi()\n\n\n@mcp.tool()\ndef tool_a():\n    return client.a()\n"
PV_PYPROJECT = """[project]
name = "demo-mcp"
version = "1.2.3"
dependencies = ["agent-connector-sdk[mcp]>=0.5.4,<0.6.0"]

[project.scripts]
demo-mcp = "demo_mcp.mcp_server:main"

[project.entry-points."agent_connector_sdk.connector"]
demo-mcp = "demo_mcp:connector"
"""


def parity_repo(tmp: Path, script: str) -> Path:
    (tmp / "pyproject.toml").write_text(PV_PYPROJECT, encoding="utf-8")
    pkg = tmp / "demo_mcp"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "api_client.py").write_text(PV_API, encoding="utf-8")
    (pkg / "mcp_server.py").write_text(PV_SERVER, encoding="utf-8")
    (tmp / "scripts").mkdir()
    shutil.copy(FIXTURES / "scripts" / f"{script}.py.txt", tmp / "scripts" / "verify_api_integration.py")
    return tmp


@pytest.mark.spec("PIPE-GATES-R016.99")
@pytest.mark.parametrize("script", ["fan-manager", "firefly-iii-mcp", "gramps-mcp", "paperless-ngx-mcp"])
def test_v_extracts_the_exact_100_percent_threshold(script: str) -> None:
    source = (FIXTURES / "scripts" / f"{script}.py.txt").read_text(encoding="utf-8")
    assert "BASELINES" not in source
    assert P._implied_baseline(source) == 100.0


@pytest.mark.spec("PIPE-GATES-R016.99")
@pytest.mark.parametrize("script", ["fan-manager", "firefly-iii-mcp", "gramps-mcp", "paperless-ngx-mcp"])
def test_v_ports_the_implied_baseline_and_deletes_the_script(tmp_path: Path, script: str) -> None:
    root = parity_repo(tmp_path, script)
    ctx = run(root, "pl.v")
    assert not blocking(ctx, "pl.v"), ctx.review.items
    assert not (root / "scripts" / "verify_api_integration.py").exists()
    assert any("below the ported baseline" in i["detail"] for i in ctx.review.items)  # 100 on its metric, 50 on ours
    assert container_table(root)["api_integration"] == {"baseline": 50.0}


@pytest.mark.spec("PIPE-GATES-R016.99")
def test_v_an_openapi_source_check_stays_blocking(tmp_path: Path) -> None:
    root = parity_repo(tmp_path, "immich-api")
    assert P._implied_baseline((root / "scripts" / "verify_api_integration.py").read_text()) is None
    ctx = run(root, "pl.v")
    (item,) = blocking(ctx, "pl.v")
    assert "--source" in item["detail"] and (root / "scripts" / "verify_api_integration.py").exists()


@pytest.mark.spec("PIPE-GATES-R016.99")
def test_v_a_script_with_another_threshold_is_not_extracted() -> None:
    assert P._implied_baseline("def main():\n    baseline = 80.0\n    return 0\n") is None
    assert P._implied_baseline('def main():\n    print("Coverage: 100.0%")\n    return 0\n') is None  # never fails


# --- pl.p: the ontology file is not called <ontology_source>.ttl (bellwether-mcp, media-downloader, world-reference) ----
def ontology_repo(tmp: Path, name: str) -> Path:
    src = FIXTURES / name
    shutil.copy(src / "pyproject.toml", tmp / "pyproject.toml")
    data = tomllib.loads((tmp / "pyproject.toml").read_text(encoding="utf-8"))
    ((_, value),) = data["project"]["entry-points"]["agent_connector_sdk.connector"].items()
    pkg = tmp / re.split(r"[:.]", str(value))[0]
    shutil.copytree(src / "ontology", pkg / "ontology")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    return tmp


@pytest.mark.spec("PIPE-GATES-R016.93")
def test_p_names_an_ontology_file_that_is_not_the_ontology_source(tmp_path: Path) -> None:
    root = ontology_repo(tmp_path, "bellwether-mcp")
    pkg = root / "bellwether_mcp" / "ontology"
    assert not (pkg / "bellwether-mcp.ttl").exists() and (pkg / "market_data.ttl").exists()
    ctx = run(root, "pl.p")
    assert not blocking(ctx, "pl.p"), ctx.review.items
    assert container_table(root)["ontology"] == {"ttl": "market_data"}
    assert not (pkg / "shapes" / "connector.shacl.ttl").exists() and not (pkg / "certification.json").exists()


@pytest.mark.spec("PIPE-GATES-R016.93")
def test_p_two_ontology_files_do_not_guess(tmp_path: Path) -> None:
    root = ontology_repo(tmp_path, "bellwether-mcp")
    pkg = root / "bellwether_mcp" / "ontology"
    shutil.copy(pkg / "market_data.ttl", pkg / "other.ttl")
    ctx = run(root, "pl.p")
    assert blocking(ctx, "pl.p") and (pkg / "shapes" / "connector.shacl.ttl").exists()


@pytest.mark.spec("PIPE-GATES-R016.93")
def test_the_ttl_key_changes_nothing_when_it_is_absent(tmp_path: Path) -> None:
    from pipelines_hooks.connector import generate

    root = ontology_repo(tmp_path, "bellwether-mcp")
    pkg = root / "bellwether_mcp" / "ontology"
    shutil.move(pkg / "market_data.ttl", pkg / "bellwether-mcp.ttl")
    shapes = {p.name: t for p, t in generate.generate(root).items()}
    assert json.loads(shapes["certification.json"])["artifacts"].get("bellwether_mcp/ontology/bellwether-mcp.ttl")
