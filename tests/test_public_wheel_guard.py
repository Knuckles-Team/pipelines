"""PIPE-RELEASE-R012.1: public wheel bytes bind to reviewed image source."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
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
