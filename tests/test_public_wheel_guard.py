"""PIPE-RELEASE-R012.1: public wheel bytes bind to reviewed image source."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shlex
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

ACTION = Path(__file__).parents[1] / ".github/actions/verify-release-version"


@pytest.fixture
def guard():
    spec = importlib.util.spec_from_file_location("public_wheel", ACTION / "public_wheel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive(files):
    data = io.BytesIO()
    with ZipFile(data, "w") as wheel:
        for name, body in files.items():
            wheel.writestr(name, body)
    return data.getvalue()


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_public_wheel_checks_exact_inventory_and_bytes(guard):
    expected = {"demo/__init__.py": b"version = '1'", "demo/ontology.ttl": b"ontology"}
    data = archive(expected | {"demo-1.dist-info/METADATA": b"metadata"})
    guard.verify_payload(data, hashlib.sha256(data).hexdigest(), expected, "demo")
    for files in (
        {"demo/__init__.py": expected["demo/__init__.py"]},
        expected | {"demo/extra.py": b"extra"},
        expected | {"demo/ontology.ttl": b"changed"},
    ):
        altered = archive(files)
        with pytest.raises(ValueError, match="inventory|payload"):
            guard.verify_payload(altered, hashlib.sha256(altered).hexdigest(), expected, "demo")
    with pytest.raises(ValueError, match="digest"):
        guard.verify_payload(b"not a zip", "0" * 64, expected, "demo")


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_public_wheel_uses_committed_source_and_refuses_stale_pin(guard, tmp_path, monkeypatch):
    for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
        monkeypatch.delenv(name, raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "demo").mkdir()
    (tmp_path / "docker").mkdir()
    (tmp_path / "demo/__init__.py").write_bytes(b"reviewed")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo-dist"\nversion="1.2.3"\n')
    (tmp_path / "docker/Dockerfile").write_text("RUN pip install demo-dist[mcp]==1.2.2\n")
    subprocess.run(
        ["git", "add", "--", "demo/__init__.py", "pyproject.toml", "docker/Dockerfile"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "demo/__init__.py").write_bytes(b"unreviewed")
    assert guard.reviewed_payload(tmp_path, "demo") == {"demo/__init__.py": b"reviewed"}
    monkeypatch.setattr(guard, "read_public", lambda url: pytest.fail("stale pin must refuse before network"))
    with pytest.raises(ValueError, match="pin"):
        guard.verify_release(tmp_path, "demo-dist", "demo", "docker/Dockerfile", "mcp")
    with pytest.raises(ValueError, match="empty"):
        guard.reviewed_payload(tmp_path, "absent")
    with pytest.raises(ValueError, match="explicit"):
        guard.reviewed_payload(tmp_path, "../demo")


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_public_wheel_binds_release_generated_connector_artifacts(guard, tmp_path, monkeypatch):
    for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
        monkeypatch.delenv(name, raising=False)
    package = tmp_path / "demo"
    (package / "ontology" / "mappings").mkdir(parents=True)
    package.joinpath("__init__.py").write_bytes(b"reviewed")
    (package / "ontology" / "mappings" / "source.yaml").write_text("ontology_source: demo\n")
    (package / "ontology" / "demo.ttl").write_text(":Book a owl:Class .\n")
    (tmp_path / "pyproject.toml").write_text(
        """[project]
name = "demo-dist"
version = "1.2.3"
[project.entry-points."agent_connector_sdk.connector"]
demo = "demo:connector"
""",
        encoding="utf-8",
    )
    paths = [
        "demo/__init__.py",
        "demo/ontology/mappings/source.yaml",
        "demo/ontology/demo.ttl",
        "pyproject.toml",
    ]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "--", *paths], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        cwd=tmp_path,
        check=True,
    )

    expected = guard.reviewed_payload(tmp_path, "demo")
    assert guard.reviewed_identity(tmp_path) == {
        "connector": True,
        "distribution": "demo-dist",
        "module": "demo",
    }
    from pipelines_hooks.connector import generate

    generated = generate.generate(tmp_path)
    for path, text in generated.items():
        name = path.relative_to(tmp_path).as_posix()
        assert name in expected and expected[name] == text.encode("utf-8")
    payload = archive(expected)
    guard.verify_payload(payload, hashlib.sha256(payload).hexdigest(), expected, "demo")


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_public_wheel_identity_skips_non_connectors_and_refuses_ambiguity(guard, tmp_path, monkeypatch):
    for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo-dist"\nversion = "1.2.3"\n')
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "--", "pyproject.toml"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        cwd=tmp_path,
        check=True,
    )
    assert guard.reviewed_identity(tmp_path) == {"connector": False}
    (tmp_path / "pyproject.toml").write_text(
        """[project]
name = "demo-dist"
version = "1.2.3"
[project.entry-points."agent_connector_sdk.connector"]
first = "demo.first"
second = "demo.second"
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "--", "pyproject.toml"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "ambiguous"],
        cwd=tmp_path,
        check=True,
    )
    with pytest.raises(ValueError, match="ambiguous"):
        guard.reviewed_identity(tmp_path)


@pytest.mark.spec("PIPE-RELEASE-R012.1")
@pytest.mark.parametrize("identity", ["entry-point", "connector-sources"])
def test_public_wheel_renders_generated_dockerfile_from_reviewed_head(guard, tmp_path, monkeypatch, identity):
    for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
        monkeypatch.delenv(name, raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo/__init__.py").write_bytes(b"reviewed")
    pyproject = """\
[project]
name = "demo-dist"
version = "1.2.3"
dependencies = ["agent-connector-sdk>=1"]

[project.optional-dependencies]
mcp = []

[project.scripts]
demo-mcp = "demo:main"
"""
    if identity == "entry-point":
        pyproject += '\n[project.entry-points."agent_connector_sdk.connector"]\ndemo-mcp = "demo"\n'
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    paths = ["demo/__init__.py", "pyproject.toml"]
    if identity == "connector-sources":
        (tmp_path / "connector_sources.py").write_text('CONNECTOR = "demo"\n', encoding="utf-8")
        paths.append("connector_sources.py")
    subprocess.run(["git", "add", "--", *paths], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        cwd=tmp_path,
        check=True,
    )

    # The guard must render from HEAD, just as the payload reader does, even if the checkout is dirty.
    (tmp_path / "pyproject.toml").write_text(
        pyproject.replace('version = "1.2.3"', 'version = "9.9.9"'), encoding="utf-8"
    )
    expected = {"demo/__init__.py": b"reviewed"}
    payload = archive(expected)
    digest = hashlib.sha256(payload).hexdigest()
    metadata = {
        "urls": [
            {
                "filename": "demo_dist-1.2.3-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/demo.whl",
                "digests": {"sha256": digest},
            }
        ]
    }
    calls = []

    def download(url):
        calls.append(url)
        return payload if url.endswith(".whl") else json.dumps(metadata).encode()

    monkeypatch.setattr(guard, "read_public", download)
    receipt = guard.verify_release(tmp_path, "demo-dist", "demo", "docker/Dockerfile", "mcp")
    assert (
        receipt["source_revision"]
        == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    )
    assert receipt["wheel_sha256"] == digest
    assert calls == ["https://pypi.org/pypi/demo-dist/1.2.3/json", "https://files.pythonhosted.org/demo.whl"]


@pytest.mark.spec("PIPE-RELEASE-R012.1")
@pytest.mark.parametrize("has_mcp_extra", [False, True])
@pytest.mark.parametrize("tracked", [False, True])
def test_public_wheel_target_extra_matches_generated_and_tracked_targets(
    guard, tmp_path, monkeypatch, has_mcp_extra, tracked
):
    for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo/__init__.py").write_bytes(b"reviewed")
    optional = "[project.optional-dependencies]\nmcp = []\n\n" if has_mcp_extra else ""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "demo-dist"\n'
        'version = "1.2.3"\n'
        'dependencies = ["agent-connector-sdk[mcp]>=1"]\n\n'
        "[project.scripts]\n"
        'demo-mcp = "demo:main"\n\n' + optional + '[project.entry-points."agent_connector_sdk.connector"]\n'
        'demo = "demo:connector"\n',
        encoding="utf-8",
    )
    expected_extra = "mcp" if has_mcp_extra else ""
    if tracked:
        docker = tmp_path / "docker/Dockerfile"
        docker.parent.mkdir()
        pin = f"demo-dist[{expected_extra}]==1.2.3" if expected_extra else "demo-dist==1.2.3"
        docker.write_text(f"FROM builder-base AS builder-mcp\nRUN pip install {pin}\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "--", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        cwd=tmp_path,
        check=True,
    )

    assert guard.reviewed_target_extra(tmp_path, "mcp") == expected_extra
    dockerfile = guard._reviewed_dockerfile(tmp_path, "docker/Dockerfile")
    pin = f"demo-dist[{expected_extra}]==1.2.3" if expected_extra else "demo-dist==1.2.3"
    assert pin in shlex.split(dockerfile, comments=True)
    expected = {"demo/__init__.py": b"reviewed"}
    payload = archive(expected)
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        guard,
        "read_public",
        lambda url: (
            payload
            if url.endswith(".whl")
            else json.dumps(
                {
                    "urls": [
                        {
                            "filename": "demo_dist-1.2.3-py3-none-any.whl",
                            "url": "https://files.pythonhosted.org/demo.whl",
                            "digests": {"sha256": digest},
                        }
                    ]
                }
            ).encode()
        ),
    )
    guard.verify_release(tmp_path, "demo-dist", "demo", "docker/Dockerfile", expected_extra)


@pytest.mark.spec("PIPE-RELEASE-R012.1")
@pytest.mark.parametrize("has_mcp_extra", [False, True])
@pytest.mark.parametrize("tracked", [False, True])
def test_public_wheel_rejects_target_pin_mismatches_before_public_fetch(
    guard, tmp_path, monkeypatch, has_mcp_extra, tracked
):
    for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
        monkeypatch.delenv(name, raising=False)
    optional = "[project.optional-dependencies]\nmcp = []\n\n" if has_mcp_extra else ""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "demo-dist"\n'
        'version = "1.2.3"\n'
        'dependencies = ["agent-connector-sdk[mcp]>=1"]\n\n'
        "[project.scripts]\n"
        'demo-mcp = "demo:main"\n\n' + optional + '[project.entry-points."agent_connector_sdk.connector"]\n'
        'demo = "demo:connector"\n',
        encoding="utf-8",
    )
    actual_extra = "mcp" if has_mcp_extra else ""
    pin = f"demo-dist[{actual_extra}]==1.2.3" if actual_extra else "demo-dist==1.2.3"
    paths = ["pyproject.toml"]
    if tracked:
        docker = tmp_path / "docker/Dockerfile"
        docker.parent.mkdir()
        docker.write_text(f"FROM builder-base AS builder-mcp\nRUN pip install {pin}\n")
        paths.append("docker/Dockerfile")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "--", *paths], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        cwd=tmp_path,
        check=True,
    )

    wrong_extra = "mcp" if not actual_extra else ""
    monkeypatch.setattr(guard, "read_public", lambda url: pytest.fail("pin mismatch must refuse before network"))
    with pytest.raises(ValueError, match="Dockerfile must pin"):
        guard.verify_release(tmp_path, "demo-dist", "demo", "docker/Dockerfile", wrong_extra)


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_public_wheel_refuses_to_render_a_nonconnector_dockerfile(guard, tmp_path, monkeypatch):
    for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
        monkeypatch.delenv(name, raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo-dist"\nversion = "1.2.3"\n', encoding="utf-8")
    subprocess.run(["git", "add", "--", "pyproject.toml"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        cwd=tmp_path,
        check=True,
    )
    with pytest.raises(ValueError, match="connector identity"):
        guard._reviewed_dockerfile(tmp_path, "docker/Dockerfile")


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_public_wheel_refuses_a_missing_custom_dockerfile(guard, tmp_path, monkeypatch):
    for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo-dist"\nversion = "1.2.3"\n'
        '[project.entry-points."agent_connector_sdk.connector"]\ndemo = "demo"\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "--", "pyproject.toml"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        cwd=tmp_path,
        check=True,
    )
    with pytest.raises(ValueError, match="not tracked"):
        guard._reviewed_dockerfile(tmp_path, "docker/custom.Dockerfile")


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_public_wheel_requires_the_provider_renderer_checkout(guard, tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "__file__", str(tmp_path / "public_wheel.py"))
    with pytest.raises(ValueError, match="provider renderer checkout"):
        guard._rendered_dockerfile(tmp_path)


@pytest.mark.spec("PIPE-RELEASE-R012.1")
def test_public_wheel_action_is_explicit_and_preserves_release_default():
    action = yaml.safe_load((ACTION / "action.yml").read_text())
    assert action["inputs"]["mode"]["default"] == "unpublished"
    steps = action["runs"]["steps"]
    old = next(step for step in steps if "verify_release_version.py" in step.get("run", ""))
    public = next(step for step in steps if "public_wheel.py" in step.get("run", ""))
    assert old["if"] == "inputs.mode == 'unpublished'"
    assert public["if"] == "inputs.mode == 'published-wheel'"
    assert all(name in public["env"] for name in ("RELEASE_DISTRIBUTION", "RELEASE_MODULE", "RELEASE_DOCKERFILE"))
    assert "python3 -I" in public["run"]


@pytest.mark.spec("PIPE-RELEASE-R012.1")
@pytest.mark.parametrize("quoted", [False, True])
def test_public_wheel_release_receipt_binds_source_and_public_bytes(guard, tmp_path, monkeypatch, quoted):
    expected = {"demo/__init__.py": b"reviewed", "demo/shapes.ttl": b"shapes"}
    payload = archive(expected)
    digest = hashlib.sha256(payload).hexdigest()
    metadata = {
        "urls": [
            {
                "filename": "demo_dist-1.2.3-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/demo.whl",
                "digests": {"sha256": digest},
            }
        ]
    }
    calls = []

    def git_output(argv, **kwargs):
        if argv[1:] == ["show", "HEAD:pyproject.toml"]:
            return '[project]\nname="demo-dist"\nversion="1.2.3"\n'
        if argv[1:] == ["show", "HEAD:docker/Dockerfile"]:
            quote = '"' if quoted else ""
            return f"RUN pip install {quote}demo-dist[mcp]==1.2.3{quote}\n"
        if argv[1:] == ["rev-parse", "HEAD"]:
            return "a" * 40 + "\n"
        raise AssertionError(argv)

    def download(url):
        calls.append(url)
        return payload if url.endswith(".whl") else json.dumps(metadata).encode()

    monkeypatch.setattr(guard.subprocess, "check_output", git_output)
    monkeypatch.setattr(guard, "reviewed_payload", lambda root, module: expected)
    monkeypatch.setattr(guard, "read_public", download)
    receipt = guard.verify_release(tmp_path, "demo-dist", "demo", "docker/Dockerfile", "mcp")
    assert receipt == {
        "package": "demo-dist",
        "module": "demo",
        "version": "1.2.3",
        "source_revision": "a" * 40,
        "wheel_sha256": digest,
        "verified_payload_files": 2,
    }
    assert calls == ["https://pypi.org/pypi/demo-dist/1.2.3/json", "https://files.pythonhosted.org/demo.whl"]
    metadata["urls"].append(metadata["urls"][0])
    with pytest.raises(ValueError, match="Exactly one"):
        guard.verify_release(tmp_path, "demo-dist", "demo", "docker/Dockerfile", "mcp")
