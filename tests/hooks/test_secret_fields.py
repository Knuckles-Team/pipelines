"""PIPE-GATES-R097: a connector's served surface never carries credential material."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from pipelines_hooks import cli
from pipelines_hooks.connector import secret_fields
from pipelines_hooks.connector.secret_scan import is_secret_name, model_leaks, recorded_leaks, schema_leaks

#: Built at run time so no credential-shaped literal is committed.
FAKE_GITLAB_TOKEN = "gl" + "pat-" + "x" * 24

PYPROJECT = """
[project]
name = "demo-api"
version = "0.0.1"

[project.entry-points."scion_sdk.connector"]
demo = "demo_api.server:build"

[tool.pipelines_hooks.secret_fields]
mode = "{mode}"
"""

RESPONSE_MODELS = """
from pydantic import BaseModel, Field, SecretStr


class Project(BaseModel):
    name: str
    runners_token: str | None = None
    token_expires_at: str | None = None
    api_key: SecretStr | None = None
    webhook_secret: str = Field(default="", exclude=True)
    minted_token: str = Field(default="", json_schema_extra={"x-secret-bearing": True})


class ProjectRequest(BaseModel):
    password: str
"""


def _git(root: Path, *args: str) -> None:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(root)}
    env |= {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)


def _connector(tmp_path: Path, mode: str = "staged") -> Path:
    root = tmp_path / "demo-api"
    (root / "demo_api").mkdir(parents=True)
    (root / "tests" / "cassettes").mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT.format(mode=mode), encoding="utf-8")
    (root / "demo_api" / "__init__.py").write_text("", encoding="utf-8")
    (root / "demo_api" / "response_models.py").write_text(RESPONSE_MODELS, encoding="utf-8")
    schema = {"type": "object", "properties": {"id": {"type": "string"}, "client_secret": {"type": "string"}}}
    (root / "demo_api" / "group.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    recorded = {"projects": [{"name": "a", "runners_token": FAKE_GITLAB_TOKEN, "password": "***"}]}
    (root / "tests" / "cassettes" / "projects.json").write_text(json.dumps(recorded), encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


@pytest.mark.spec("PIPE-GATES-R097")
def test_secret_names_end_in_a_credential_word() -> None:
    for name in ("runners_token", "runnersToken", "api_key", "webhook_secret", "connection_string", "private_key"):
        assert is_secret_name(name), name
    for name in ("token_expires_at", "api_key_env", "has_password", "special_tokens", "continuation_token"):
        assert not is_secret_name(name), name


@pytest.mark.spec("PIPE-GATES-R097")
def test_an_unmarked_secret_field_of_a_response_model_is_reported() -> None:
    leaks = model_leaks("demo_api/response_models.py", RESPONSE_MODELS)
    assert [(leak.code, leak.detail) for leak in leaks] == [("SF-MODEL-FIELD", "Project.runners_token")]
    assert leaks[0].render() == "demo_api/response_models.py:7 SF-MODEL-FIELD Project.runners_token"


@pytest.mark.spec("PIPE-GATES-R097")
def test_a_schema_property_needs_a_redaction_or_secret_bearing_mark() -> None:
    schema = {
        "properties": {
            "token": {"type": "string"},
            "minted": {"properties": {"password": {"type": "string", "x-secret-bearing": True}}},
            "items": {"type": "array", "items": {"properties": {"private_key": {"writeOnly": True}}}},
        }
    }
    assert [leak.detail for leak in schema_leaks("tool:x", schema)] == ["token"]


@pytest.mark.spec("PIPE-GATES-R097")
def test_a_recorded_output_with_a_credential_value_is_reported_without_the_value() -> None:
    text = json.dumps({"runners_token": FAKE_GITLAB_TOKEN, "password": "<redacted>", "name": "x"})
    leaks = recorded_leaks("tests/cassettes/p.json", text)
    assert {(leak.code, leak.detail) for leak in leaks} == {
        ("SF-RECORDED-VALUE", "gitlab-token"),
        ("SF-RECORDED-FIELD", "runners_token"),
    }
    assert all(FAKE_GITLAB_TOKEN not in leak.render() for leak in leaks)


@pytest.mark.spec("PIPE-GATES-R097")
def test_staged_mode_lists_every_offender_and_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _connector(tmp_path)
    assert secret_fields.main(["--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "demo_api/response_models.py:7 SF-MODEL-FIELD Project.runners_token" in out
    assert "demo_api/group.schema.json:1 SF-SCHEMA-FIELD client_secret" in out
    assert "tests/cassettes/projects.json" in out and FAKE_GITLAB_TOKEN not in out
    assert "secret-fields: 4 finding(s) in demo_api (mode staged)" in out


@pytest.mark.spec("PIPE-GATES-R097")
def test_blocking_mode_exits_one_and_a_non_connector_passes(tmp_path: Path) -> None:
    assert cli.main(["secret-fields", "--root", str(_connector(tmp_path / "a", mode="blocking"))]) == 1
    plain = tmp_path / "plain"
    plain.mkdir()
    _git(plain, "init", "-q", "-b", "main")
    assert cli.main(["secret-fields", "--root", str(plain)]) == 0


@pytest.mark.spec("PIPE-GATES-R097")
def test_the_probe_checks_the_output_schema_of_every_served_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _connector(tmp_path)
    schemas = {"gitlab_get_projects": {"properties": {"runners_token": {"type": "string"}}}, "ok": {}}
    fake = tmp_path / "fake-python"
    fake.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            print({secret_fields.MARKER!r} + {json.dumps(json.dumps(schemas))})
            """
        ),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PIPELINES_CONNECTOR_PYTHON", str(fake))
    assert secret_fields.main(["--root", str(root), "--probe"]) == 0
    assert "tool:gitlab_get_projects:1 SF-SERVED-OUTPUT-FIELD runners_token" in capsys.readouterr().out
