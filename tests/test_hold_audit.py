"""A held pull request is never armed for auto-merge (PIPE-GATES-R062)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_held_pull_requests as audit  # noqa: E402


def _pr(number: int, labels: list[str], armed: bool) -> dict:
    return {
        "number": number,
        "labels": [{"name": name} for name in labels],
        "auto_merge": {"merge_method": "merge"} if armed else None,
    }


def _api(prs: dict[str, list[dict]]):
    calls: list[str] = []

    def get(path: str) -> object:
        calls.append(path)
        name = path.split("/")[2]
        return prs[name] if path.endswith("&page=1") else []

    get.calls = calls  # type: ignore[attr-defined]
    return get


@pytest.mark.spec("PIPE-GATES-R062")
def test_a_held_pull_request_with_an_armed_merge_is_a_finding(capsys: pytest.CaptureFixture[str]) -> None:
    api = _api({"demo": [_pr(5, ["hold"], True), _pr(6, ["bug"], True)]})
    assert audit.armed_held(api, "Org", "demo") == ["demo#5: carries the 'hold' label and has an armed merge request"]
    assert audit.main(["--repo", "demo"], api=api) == 1
    assert "demo#5" in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R062")
def test_an_unarmed_held_pull_request_passes() -> None:
    api = _api({"demo": [_pr(5, ["hold"], False), _pr(6, [], False)]})
    assert audit.armed_held(api, "Org", "demo") == []
    assert audit.main(["--repo", "demo"], api=api) == 0


@pytest.mark.spec("PIPE-GATES-R062")
def test_the_audit_only_reads() -> None:
    api = _api({"demo": [_pr(5, ["hold"], True)]})
    audit.main(["--repo", "demo"], api=api)
    assert api.calls and all("/pulls?state=open" in call for call in api.calls)  # type: ignore[attr-defined]
    source = (ROOT / "scripts/audit_held_pull_requests.py").read_text(encoding="utf-8")
    for verb in ("POST", "PUT", "PATCH", "DELETE", "-X "):
        assert verb not in source
    workflow = yaml.safe_load((ROOT / ".github/workflows/hold_audit.yml").read_text(encoding="utf-8"))
    assert workflow["permissions"] == {"contents": "read"}
    assert "scripts/audit_held_pull_requests.py" in workflow["jobs"]["audit"]["steps"][1]["run"]
