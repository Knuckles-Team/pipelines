"""The published hook catalogue, the CLI registry and this repository's self-run agree."""

from __future__ import annotations

import yaml

from pipelines_hooks.cli import ALIASES, GATES, GROUPS, main
from tests.hooks.conftest import HOOK_REPOSITORY


def _catalogue() -> dict[str, dict]:
    hooks = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    return {hook["id"]: hook for hook in hooks}


def test_every_catalogue_entry_runs_a_registered_gate() -> None:
    for hook_id, hook in _catalogue().items():
        command = hook["entry"].split()
        assert command[0] == "pipelines-hook", hook_id
        assert command[1] in {*GATES, *GROUPS, *ALIASES}, hook_id


def test_every_registered_gate_is_published() -> None:
    published = {hook["entry"].split()[1] for hook in _catalogue().values()}
    assert published == {*GATES, *GROUPS, *ALIASES}


STANDARD = {"secrets", "spec", "tests-fast"}
KEPT = {
    "agent-contract",
    "connector-graphql",
    "connector-name",
    "coupling",
    "lockfile-version-mirrors",
    "sdk-conformance",
    "no-legacy-concepts",
    "dependency-readiness",
    "gate-set",
    "pr-test-scope",
    "uv-lock-check",
    "validate",
}


def test_only_the_standard_hooks_are_current() -> None:
    current = {hook_id for hook_id, hook in _catalogue().items() if not hook["name"].startswith("DEPRECATED")}
    assert current == STANDARD | KEPT


def test_groups_name_registered_gates_only() -> None:
    assert all(member in GATES for members in GROUPS.values() for member in members)
    assert all(target in GATES for target in ALIASES.values())


def test_a_group_honours_skip_and_reports_the_worst_status(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake(gate: str, argv: list[str]) -> int:
        calls.append(gate)
        return 1 if gate == "spec-status" else 0

    monkeypatch.setattr("pipelines_hooks.cli.run_gate", fake)
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", "HEAD")
    monkeypatch.setenv("SKIP", "spec-trailers,unrelated")
    assert main(["spec"]) == 1
    assert calls == ["spec-standard", "spec-decomposition", "spec-status"]
    assert "spec-trailers skipped (SKIP)" in capsys.readouterr().out
    assert main(["spec", "--root", "."]) == 2


def test_range_members_run_only_with_a_commit_range(monkeypatch, capsys) -> None:
    calls: list[str] = []
    monkeypatch.setattr("pipelines_hooks.cli.run_gate", lambda gate, argv: calls.append(gate) or 0)
    monkeypatch.delenv("SKIP", raising=False)
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    assert main(["secrets"]) == 0
    assert calls == ["security-sanitizer", "tracked-privacy", "commit-identity"]
    assert "secret-history runs at push" in capsys.readouterr().out
    calls.clear()
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", "HEAD")
    assert main(["secrets"]) == 0
    assert calls == list(GROUPS["secrets"])


def test_tests_fast_is_the_fast_tests_gate(monkeypatch) -> None:
    seen: list[tuple[str, list[str]]] = []
    monkeypatch.setattr("pipelines_hooks.cli.run_gate", lambda gate, argv: seen.append((gate, list(argv))) or 0)
    assert main(["tests-fast", "--src-root", "pkg"]) == 0
    assert seen == [("fast-tests", ["--src-root", "pkg"])]


def test_this_repository_runs_its_hooks_with_the_published_entries() -> None:
    config = yaml.safe_load((HOOK_REPOSITORY / ".config" / "pre-commit.yaml").read_text(encoding="utf-8"))
    local = {hook["id"]: hook for repo in config["repos"] if repo["repo"] == "local" for hook in repo["hooks"]}
    catalogue = _catalogue()
    self_run = {hook_id: hook for hook_id, hook in local.items() if hook_id in catalogue}
    assert self_run, "the repository runs none of its own hooks"
    for hook_id, hook in self_run.items():
        assert hook["entry"].endswith(catalogue[hook_id]["entry"]), hook_id


def test_ste_census_hooks_run_only_at_push_or_manual() -> None:
    for hook_id in ("ste-census", "ste-staleness-census"):
        assert _catalogue()[hook_id].get("stages") == ["pre-push", "manual"]
