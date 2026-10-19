"""PIPE-RELEASE-R002: immutable release source and fail-closed tag preflight."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.core.gitenv import sanitized_env
from tests.workflow_fixtures import runtime_checkout

ROOT = Path(__file__).parents[1]
ACTION = ROOT / ".github/actions/verify-release-source"
RELEASE = ROOT / ".github/actions/create-version-release/action.yml"


@pytest.fixture
def guard():
    spec = importlib.util.spec_from_file_location("release_source_guard", ACTION / "verify_release_source.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["clean", "pre-push"])
def git_context(tmp_path, monkeypatch, request):
    if request.param == "pre-push":
        outer = tmp_path / "outer"
        outer.mkdir()
        runtime_checkout(outer)
        for key, value in {
            "GIT_DIR": outer / ".git",
            "GIT_WORK_TREE": outer,
            "GIT_INDEX_FILE": outer / ".git/index",
        }.items():
            monkeypatch.setenv(key, str(value))
    # Push-hook Git selectors must never redirect fixture commands.
    for key in set(os.environ) - sanitized_env().keys():
        monkeypatch.delenv(key)


@pytest.fixture
def case(tmp_path, monkeypatch, git_context):
    source = runtime_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    environment = {
        "SOURCE_COMMIT": source,
        "LATEST_COMMIT": source,
        "EXPECTED_COMMIT": source,
        "RELEASE_REPOSITORY": "Example/package",
        "RELEASE_API_URL": "https://api.github.com",
        "RELEASE_TOKEN": "fixture-read-token",
        "BUILD_VERSION": "1.2.3",
        "GITHUB_OUTPUT": str(tmp_path / "output"),
    }
    return environment


def serve(monkeypatch, guard, responses):
    """Exercise the real request builder with an in-memory GitHub transport."""
    from io import BytesIO
    from urllib.error import HTTPError

    calls = []

    class Transport:
        def open(self, request, *, timeout):
            calls.append(request)
            assert timeout == 15 and request.get_method() == "GET"
            assert request.headers["Authorization"] == "Bearer fixture-read-token"
            value = responses[request.full_url.removeprefix("https://api.github.com")]
            if isinstance(value, int):
                raise HTTPError(request.full_url, value, "fixture", {}, None)
            return BytesIO(json.dumps(value).encode())

    monkeypatch.setattr(guard, "build_opener", lambda *args: Transport())
    return calls


def test_default_branch_advance_cannot_retarget_release(guard, case, monkeypatch, tmp_path):
    source = case["SOURCE_COMMIT"]
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-qm",
            "branch advances",
        ],
        check=True,
        env=sanitized_env(),
    )
    advanced = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "checkout", "--detach", source], check=True, capture_output=True)
    calls = serve(
        monkeypatch,
        guard,
        {
            "/repos/Example/package": {"full_name": "Example/package", "default_branch": "main"},
            "/repos/Example/package/git/ref/tags/v1.2.3": 404,
        },
    )
    for key, value in case.items():
        monkeypatch.setenv(key, value)
    assert guard.main() == 0
    verified = (tmp_path / "output").read_text().strip().split("=", 1)[1]
    release = yaml.safe_load(RELEASE.read_text())["runs"]["steps"][-1]
    assert release["with"]["target_commitish"] == "${{ steps.release_source.outputs.commit }}"
    subprocess.run(["git", "tag", "v1.2.3", verified], check=True, env=sanitized_env())
    tagged = subprocess.check_output(["git", "rev-parse", "v1.2.3"], text=True).strip()
    assert tagged == source != advanced
    assert len(calls) == 2


@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("conflict", [False, True])
def test_existing_tag_is_compared_to_frozen_source(guard, case, monkeypatch, annotated, conflict):
    expected = case["SOURCE_COMMIT"]
    target = "b" * 40 if conflict else expected
    responses = {
        "/repos/Example/package": {"full_name": "Example/package"},
        "/repos/Example/package/git/ref/tags/v1.2.3": {
            "ref": "refs/tags/v1.2.3",
            "object": {"type": "tag" if annotated else "commit", "sha": "a" * 40 if annotated else target},
        },
        "/repos/Example/package/git/tags/" + "a" * 40: {"sha": "a" * 40, "object": {"type": "commit", "sha": target}},
    }
    serve(monkeypatch, guard, responses)
    if conflict:
        for key, value in case.items():
            monkeypatch.setenv(key, value)
        assert guard.main() == 1
        assert not Path(case["GITHUB_OUTPUT"]).exists()
    else:
        assert guard.verify(case) == expected


@pytest.mark.parametrize("field", ["SOURCE_COMMIT", "LATEST_COMMIT", "EXPECTED_COMMIT"])
def test_source_drift_blocks_before_network(guard, case, monkeypatch, field):
    case[field] = "c" * 40
    calls = serve(monkeypatch, guard, {})
    with pytest.raises(ValueError, match="frozen"):
        guard.verify(case)
    assert calls == []


@pytest.mark.parametrize(
    "endpoint,status",
    [
        ("/repos/Example/package", 404),
        ("/repos/Example/package/git/ref/tags/v1.2.3", 401),
        ("/repos/Example/package/git/ref/tags/v1.2.3", 403),
        ("/repos/Example/package/git/ref/tags/v1.2.3", 429),
        ("/repos/Example/package/git/ref/tags/v1.2.3", 500),
    ],
)
def test_unavailable_metadata_cannot_count_as_absent_tag(guard, case, monkeypatch, endpoint, status):
    responses = {"/repos/Example/package": {"full_name": "Example/package"}, endpoint: status}
    serve(monkeypatch, guard, responses)
    with pytest.raises(ValueError, match=f"HTTP {status}"):
        guard.verify(case)


@pytest.mark.parametrize(
    "target",
    [
        {"type": "tree", "sha": "a" * 40},
        {"type": "commit", "sha": "main"},
        {"type": "tag", "sha": "a" * 40},
    ],
)
def test_unsupported_or_cyclic_tag_refuses(guard, case, monkeypatch, target):
    responses = {
        "/repos/Example/package": {"full_name": "Example/package"},
        "/repos/Example/package/git/ref/tags/v1.2.3": {"ref": "refs/tags/v1.2.3", "object": target},
        "/repos/Example/package/git/tags/" + "a" * 40: {"sha": "a" * 40, "object": target},
    }
    calls = serve(monkeypatch, guard, responses)
    with pytest.raises(ValueError):
        guard.verify(case)
    assert len(calls) <= 10


def test_conflict_created_after_preflight_is_rechecked(guard, case, monkeypatch):
    responses = {
        "/repos/Example/package": {"full_name": "Example/package"},
        "/repos/Example/package/git/ref/tags/v1.2.3": 404,
    }
    serve(monkeypatch, guard, responses)
    assert guard.verify(case) == case["SOURCE_COMMIT"]
    responses["/repos/Example/package/git/ref/tags/v1.2.3"] = {
        "ref": "refs/tags/v1.2.3",
        "object": {"type": "commit", "sha": "b" * 40},
    }
    with pytest.raises(ValueError, match="conflicts"):
        guard.verify(case)
