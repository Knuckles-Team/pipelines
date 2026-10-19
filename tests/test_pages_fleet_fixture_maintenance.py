"""Fixture commits must not start writers racing read-only fleet verification."""

import json

import pages_fleet_fixtures as fixtures


def test_fixture_commit_never_starts_automatic_maintenance(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    fixtures.repository(repository)
    fixtures.git(repository, "config", "maintenance.auto", "true")
    fixtures.git(repository, "config", "maintenance.strategy", "incremental")
    fixtures.git(repository, "config", "maintenance.loose-objects.auto", "1")
    (repository / "tracked.txt").write_text("Fixture content")
    trace = tmp_path / "git-trace.json"
    environment = fixtures.sanitized_env() | {"GIT_TRACE2_EVENT": str(trace)}
    monkeypatch.setattr(fixtures, "sanitized_env", lambda: environment)
    fixtures.commit(repository)
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    children = [event["argv"] for event in events if event["event"] == "child_start"]
    assert not any("maintenance" in command for command in children), children
