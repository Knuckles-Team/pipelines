"""The ruleset audit reports drift from `CI required` and never changes a repository (PIPE-GATES-R048)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_ruleset_conformance as audit  # noqa: E402


def _rules(*contexts: str) -> list[dict]:
    checks = [{"context": c} for c in contexts]
    return [{"type": "deletion"}, {"type": "required_status_checks", "parameters": {"required_status_checks": checks}}]


def _api(repos: dict[str, dict]):
    calls: list[str] = []

    def get(path: str) -> object:
        calls.append(path)
        name = path.split("/")[2]
        repo = repos[name]
        if path.endswith("/rules/branches/main"):
            return repo["rules"]
        return {
            "archived": repo.get("archived", False),
            "default_branch": "main",
            "allow_auto_merge": repo.get("auto", True),
        }

    get.calls = calls  # type: ignore[attr-defined]
    return get


@pytest.mark.spec("PIPE-GATES-R048")
def test_a_wrong_or_missing_required_check_is_drift() -> None:
    api = _api(
        {
            "good": {"rules": _rules("CI required")},
            "old": {"rules": _rules("gates / gates")},
            "extra": {"rules": _rules("CI required", "pytest")},
            "none": {"rules": _rules()},
        }
    )
    found = audit.audit(api, "o", ["good", "old", "extra", "none"], exclude={})
    assert [f.split(":")[0] for f in found] == ["old", "extra", "none"]
    assert "no required check" in found[2]


@pytest.mark.spec("PIPE-GATES-R048")
def test_archived_and_excluded_repositories_are_skipped_and_auto_merge_is_checked() -> None:
    api = _api(
        {
            "dead": {"rules": _rules(), "archived": True},
            "later": {"rules": _rules()},
            "manual": {"rules": _rules("CI required"), "auto": False},
        }
    )
    found = audit.audit(api, "o", ["dead", "later", "manual"], exclude={"later": "reason"})
    assert found == ["manual: allow_auto_merge is off"]


@pytest.mark.spec("PIPE-GATES-R048")
def test_main_prints_the_list_exits_one_and_only_reads(capsys: pytest.CaptureFixture[str]) -> None:
    api = _api({"old": {"rules": _rules("pytest")}})
    assert audit.main(["--repo", "old"], api=api) == 1
    out = capsys.readouterr().out
    assert "DRIFT old: main requires [pytest]" in out
    assert "medulla (excluded until its 3.0.0 landing merges)" in out
    assert all(call.startswith("repos/") for call in api.calls)  # type: ignore[attr-defined]


@pytest.mark.spec("PIPE-GATES-R048")
def test_the_registry_lists_the_fleet_and_the_workflow_is_scheduled_and_read_only() -> None:
    owner, names = audit.registry_repos()
    assert owner == "Knuckles-Team"
    assert {"arbora", "scion-sdk", ".github"} <= set(names)
    flow = yaml.safe_load((ROOT / ".github/workflows/ruleset_audit.yml").read_text(encoding="utf-8"))
    assert flow[True]["schedule"] and "workflow_dispatch" in flow[True]
    assert flow["permissions"] == {"contents": "read"}
    assert "audit_ruleset_conformance.py" in flow["jobs"]["audit"]["steps"][-1]["run"]
