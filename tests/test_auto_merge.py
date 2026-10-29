"""Fleet auto-merge gate (PIPE-GATES-R016.116) and its workflow/template shape."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts import auto_merge as am

ROOT = Path(__file__).parents[1]
SHA = "a" * 40
REPO = "Knuckles-Team/demo"


def _pull(sha=SHA, number=7):
    return {
        "number": number,
        "state": "open",
        "draft": False,
        "base": {"ref": "main", "repo": {"full_name": REPO}},
        "head": {"sha": sha},
    }


def _branch(contexts):
    return {
        "protected": True,
        "protection": {
            "required_status_checks": {
                "enforcement_level": "everyone",
                "contexts": contexts,
            }
        },
    }


def _runs(name="CI required", conclusion="success", sha=SHA, status="completed"):
    return {
        "check_runs": [
            {
                "id": 1,
                "name": name,
                "head_sha": sha,
                "status": status,
                "conclusion": conclusion,
            }
        ]
    }


def _rules(contexts):
    return [
        {"type": "deletion"},
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": c} for c in contexts]},
        },
    ]


def _api(contexts=("CI required",), runs=None, pull=None, pulls=None, ruleset_contexts=()):
    def get(path):
        if "/check-runs" in path:
            return runs if runs is not None else _runs()
        if "/rules/branches/main" in path:
            return _rules(list(ruleset_contexts))
        if "/branches/main" in path:
            if not contexts:
                raise am.ApiFailure("HTTP 404: Branch not protected")
            return _branch(list(contexts))
        if "/commits/" in path and "/pulls" in path:
            return pulls if pulls is not None else [_pull()]
        if "/pulls/" in path:
            return pull if pull is not None else _pull()
        raise AssertionError(path)

    return get


def _run(event_name, event, api, **kw):
    merged = []
    try:
        am.run_gate(
            event_name=event_name,
            event=event,
            repo=REPO,
            api_get=api,
            merge=lambda n, s: merged.append((n, s)),
            log=lambda _m: None,
            **kw,
        )
    except am.GateNotReady:
        pass  # the safe no-op: main() prints "not armed" and exits 0
    return merged


PR_EVENT = {"number": 7}
CHECK_EVENT = {"check_run": {"name": "CI required", "conclusion": "success", "head_sha": SHA}}


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_arms_on_pr_open_when_required_check_already_green():
    assert _run("pull_request_target", PR_EVENT, _api()) == [(7, SHA)]


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_does_not_merge_when_required_check_not_success_on_head():
    for runs in (
        _runs(conclusion="failure"),
        _runs(status="in_progress", conclusion=None),
        _runs(sha="b" * 40),
        {"check_runs": []},
    ):
        assert _run("pull_request_target", PR_EVENT, _api(runs=runs)) == []


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_merges_on_check_run_success_for_head_sha():
    assert _run("check_run", CHECK_EVENT, _api()) == [(7, SHA)]


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_ignores_other_check_names():
    other = {"check_run": {"name": "gates / gates", "conclusion": "success", "head_sha": SHA}}
    assert _run("check_run", other, _api()) == []
    failed = {"check_run": {"name": "CI required", "conclusion": "failure", "head_sha": SHA}}
    assert _run("check_run", failed, _api()) == []
    # only a differently named run is green on the head: not enough
    assert _run("pull_request_target", PR_EVENT, _api(runs=_runs(name="lint"))) == []


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_refuses_when_no_required_check_is_configured():
    assert _run("pull_request_target", PR_EVENT, _api(contexts=())) == []
    assert _run("pull_request_target", PR_EVENT, _api(contexts=("gates / gates",))) == []
    assert _run("pull_request_target", PR_EVENT, _api(), required_check=" ") == []


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_required_check_name_is_configurable():
    api = _api(contexts=("Fleet ok",), runs=_runs(name="Fleet ok"))
    assert _run("pull_request_target", PR_EVENT, api, required_check="Fleet ok") == [(7, SHA)]
    assert _run("pull_request_target", PR_EVENT, api) == []


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_draft_and_non_main_pulls_are_not_armed():
    draft = _pull()
    draft["draft"] = True
    assert _run("pull_request_target", PR_EVENT, _api(pull=draft)) == []
    other = _pull()
    other["base"]["ref"] = "dev"
    assert _run("pull_request_target", PR_EVENT, _api(pull=other)) == []


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_reusable_workflow_and_templates_are_wired():
    reusable = yaml.safe_load((ROOT / ".github/workflows/auto_merge_pipeline.yml").read_text())
    trig = reusable.get("on") or reusable[True]
    assert trig["workflow_call"]["inputs"]["required-check"]["default"] == "CI required"
    assert trig["workflow_call"]["secrets"]["merge-token"]["required"] is False
    assert "contents/scripts/auto_merge.py?ref=main" in (ROOT / ".github/workflows/auto_merge_pipeline.yml").read_text()
    caller = yaml.safe_load((ROOT / "templates/workflows/auto_merge.yml").read_text())
    assert caller["jobs"]["auto-merge"]["uses"].endswith("auto_merge_pipeline.yml@main")
    assert (ROOT / ".github/workflows/auto_merge.yml").read_text() == (
        ROOT / "templates/workflows/auto_merge.yml"
    ).read_text()


@pytest.mark.spec("PIPE-GATES-R016.116")
@pytest.mark.parametrize("path", [".github/workflows/ci.yml", "templates/workflows/ci.yml"])
def test_ci_required_aggregate_job(path):
    wf = yaml.safe_load((ROOT / path).read_text())
    job = wf["jobs"]["ci-required"]
    assert job["name"] == "CI required"
    assert job["if"] == "always()"
    assert job["timeout-minutes"] == 5
    assert "failure|cancelled" in job["steps"][0]["run"]


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_settings_script_refuses_without_green_check_and_has_dry_run():
    text = (ROOT / "scripts/apply_repo_ci_settings.sh").read_text()
    assert "--dry-run" in text and "exit 2" in text
    assert text.index("refusing") < text.index("gh api -X PATCH")


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_required_check_from_ruleset_without_classic_protection():
    """Repos protected only by a ruleset (no classic protection, HTTP 404) still arm."""
    api = _api(contexts=(), ruleset_contexts=("CI required",))
    am._check_required_rule(repo=REPO, required_check="CI required", api_get=api, log=lambda _m: None)


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_ruleset_requiring_another_check_refuses():
    api = _api(contexts=(), ruleset_contexts=("gates / gates",))
    with pytest.raises(am.GateNotReady):
        am._check_required_rule(repo=REPO, required_check="CI required", api_get=api, log=lambda _m: None)


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_no_classic_protection_and_no_ruleset_refuses():
    api = _api(contexts=(), ruleset_contexts=())
    with pytest.raises(am.GateNotReady):
        am._check_required_rule(repo=REPO, required_check="CI required", api_get=api, log=lambda _m: None)
