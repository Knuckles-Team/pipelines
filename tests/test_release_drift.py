"""Release drift audit (PIPE-RELEASE-R027) with a fake HTTP layer."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_drift  # noqa: E402

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _fake(repos: dict, index: dict):
    def get(url, token=None, raw=False):
        if url.startswith("https://pypi.org/pypi/"):
            name = url.split("/")[-2]
            return json.dumps({"releases": {v: [] for v in index[name]}}).encode() if name in index else None
        slug = url.split("/repos/Org/")[1].split("/")[0]
        r = repos.get(slug)
        if r is None:
            return None
        if url.endswith("/contents/pyproject.toml"):
            return None if r.get("pyproject") is None else r["pyproject"].encode()
        if "/commits/" in url:
            return json.dumps(
                {"commit": {"committer": {"date": r["when"].isoformat().replace("+00:00", "Z")}}}
            ).encode()
        return json.dumps({"default_branch": "main", "archived": r.get("archived", False)}).encode()

    return get


def _toml(name="Some_Pkg", version="1.2.0"):
    return f'[project]\nname = "{name}"\nversion = "{version}"\n'


def _run(repos, index):
    registry = {"owner": "Org", "repositories": [{"slug": s} for s in repos]}
    return release_drift.audit(registry, NOW, None, _fake(repos, index))


OLD = NOW - timedelta(hours=30)


def test_an_unpublished_old_version_is_reported_with_a_normalized_name() -> None:
    # spec: PIPE-RELEASE-R027
    out = _run({"a": {"pyproject": _toml(), "when": OLD}}, {"some-pkg": ["1.1.0"]})
    assert len(out) == 1 and "a: main has Some_Pkg 1.2.0 (unpublished)" in out[0]


def test_a_published_version_a_fresh_head_and_a_non_python_repo_are_clean() -> None:
    # spec: PIPE-RELEASE-R027
    repos = {
        "ok": {"pyproject": _toml(), "when": OLD},
        "fresh": {"pyproject": _toml("fresh"), "when": NOW - timedelta(hours=2)},
        "docs": {"pyproject": None, "when": OLD},
        "gone": {"pyproject": _toml("gone"), "when": OLD, "archived": True},
    }
    assert _run(repos, {"some-pkg": ["1.2.0"], "fresh": []}) == []


def test_a_project_missing_from_the_index_is_reported_and_nothing_is_excluded() -> None:
    # spec: PIPE-RELEASE-R027
    repos = {"new": {"pyproject": _toml("new"), "when": OLD}}
    out = _run(repos, {})
    assert len(out) == 1 and "(not on the index)" in out[0]
    assert release_drift.EXCLUDED == {}


def test_the_workflow_is_scheduled_read_only_and_runs_the_script() -> None:
    # spec: PIPE-RELEASE-R027
    wf = yaml.safe_load((ROOT / ".github/workflows/release_drift.yml").read_text())
    assert wf[True]["schedule"] and wf["permissions"] == {"contents": "read"}
    assert "scripts/release_drift.py" in json.dumps(wf["jobs"]["drift"]["steps"])


def test_transient_server_errors_retry_with_bounded_backoff(monkeypatch):
    # spec: PIPE-RELEASE-R027
    import io
    import urllib.error

    sleeps, calls = [], {"n": 0}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def flaky(req, timeout=0):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(req.full_url, 504, "Gateway Timeout", {}, None)
        return Resp(b"ok")

    monkeypatch.setattr(release_drift.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(release_drift.time, "sleep", sleeps.append)
    assert release_drift._get("https://pypi.org/pypi/x/json") == b"ok"
    assert sleeps == [2.0, 4.0]

    def always(req, timeout=0):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 504, "Gateway Timeout", {}, None)

    calls["n"] = 0
    monkeypatch.setattr(release_drift.urllib.request, "urlopen", always)
    try:
        release_drift._get("https://pypi.org/pypi/x/json")
    except urllib.error.HTTPError as exc:
        assert exc.code == 504
    assert calls["n"] == release_drift.ATTEMPTS
