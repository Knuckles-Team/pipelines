"""Source-only charts retain exact scope and refuse unsupported source evidence."""

import json
import subprocess
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from tests.git_fixture_environment import fixture_git_environment
from scripts.architecture_explorer.story_chart_sources import capture_git, source_chart
from scripts.architecture_explorer.story_contract import ContractError
from scripts.architecture_explorer.story_sources import SourceGap
from pipelines_hooks.core.errors import CannotRun

pytestmark = pytest.mark.spec("PIPE-PAGES-R042")
REPO = {"id": "R_1", "fullName": "Knuckles-Team/pipelines", "url": "https://github.com/Knuckles-Team/pipelines"}
SHA = "a" * 40
A, B = "PIPE-DEMO-R001", "PIPE-DEMO-R002"


def inputs():
    docs = {
        "specs/demo/requirements.md": f"| `{A}` | **First**. | tests |\n| `{B}` | **Second**. Depends-on: `{A}`. | tests |\n",
        "specs/demo/status.json": json.dumps(
            {
                "schema_version": 2,
                "owner_repo": "pipelines",
                "delivery_state": "SPECIFIED",
                "requirement_ids": [A, B],
                "spec_id": "PIPE-DEMO",
                "requirements": [
                    {"id": r, "delivery_state": "SPECIFIED", "landed_in": [], "verified_by": []} for r in [A, B]
                ],
            }
        ),
    }
    return {
        "repositories": [REPO],
        "selection": ["R_1:demo"],
        "captures": [
            {"repositoryId": "R_1", "head": SHA, "tree": {"truncated": False, "paths": list(docs)}, "documents": docs}
        ],
    }


def test_source_chart_complete_scope_not_model_or_activity():
    result = source_chart(**inputs())
    assert result["activity"] == {"state": "not_collected"}
    assert result["modelMapping"] == {"state": "not_qualified"}
    assert result["scope"]["fleetComplete"] is False
    assert result["scope"]["scoreRowCount"] == 2
    assert result["rows"]["R_1:" + A]["priority"]["value"] == 2
    assert result["rows"]["R_1:" + B]["priority"]["value"] == 0
    assert result["families"][0]["readyRowKeys"] == ["R_1:" + A]
    assert result["families"][0]["blockedRowKeys"] == ["R_1:" + B]
    assert result["rows"]["R_1:" + A]["provenance"]["commit"] == SHA


def test_done_is_na_not_zero():
    data = inputs()
    docs = data["captures"][0]["documents"]
    status = json.loads(docs["specs/demo/status.json"])
    status["requirements"][0]["delivery_state"] = "LANDED"
    docs["specs/demo/status.json"] = json.dumps(status)
    result = source_chart(**data)
    assert result["rows"]["R_1:" + A]["priority"]["state"] == "not_applicable"
    assert "value" not in result["rows"]["R_1:" + A]["priority"]
    assert result["rows"]["R_1:" + B]["readiness"] == "ready"


def test_cycle_preserves_shared_frontier():
    data = inputs()
    docs = data["captures"][0]["documents"]
    docs["specs/demo/requirements.md"] = docs["specs/demo/requirements.md"].replace(
        "**First**.", f"**First**. Depends-on: `{B}`."
    )
    result = source_chart(**data)
    assert result["dependencyCycles"] == [["R_1:" + A, "R_1:" + B]]
    assert result["families"][0]["readyRowKeys"] == []


def alias_input(alias='"PIPE-DEMO-R009" = "PIPE-DEMO-R001"'):
    data = inputs()
    capture = data["captures"][0]
    capture["tree"]["paths"].append(".config/spec-aliases.toml")
    capture["documents"][".config/spec-aliases.toml"] = alias
    capture["documents"]["specs/demo/requirements.md"] = capture["documents"]["specs/demo/requirements.md"].replace(
        f"Depends-on: `{A}`", "Depends-on: `PIPE-DEMO-R009`"
    )
    return data


def test_alias_retains_original_and_shared_canonical_target():
    result = source_chart(**alias_input())
    dep = result["rows"]["R_1:" + B]["dependencies"]
    assert dep["keys"] == ["R_1:" + A]
    assert dep["resolutions"][0]["declaredId"] == "PIPE-DEMO-R009"
    assert dep["resolutions"][0]["aliasProvenance"]["commit"] == SHA


@pytest.mark.parametrize(
    "alias",
    [
        '"PIPE-DEMO-R009" = "PIPE-DEMO-R008"',
        '"PIPE-DEMO-R001" = "PIPE-DEMO-R002"',
        '"PIPE-DEMO-R009" = "PIPE-DEMO-R008"\n"PIPE-DEMO-R008" = "PIPE-DEMO-R001"',
    ],
)
def test_bad_standard_alias_blocked(alias):
    with pytest.raises(CannotRun):
        source_chart(**alias_input(alias))


def test_exact_alias_does_not_map_children():
    data = alias_input()
    data["captures"][0]["documents"]["specs/demo/requirements.md"] = data["captures"][0]["documents"][
        "specs/demo/requirements.md"
    ].replace("Depends-on: `PIPE-DEMO-R009`", "Depends-on: `PIPE-DEMO-R009.1`")
    with pytest.raises(ContractError, match="unresolved"):
        source_chart(**data)


@pytest.mark.parametrize(
    "mutation",
    ["truncated", "missing_pair", "short_sha", "missing_alias", "missing_target", "duplicate_repo", "selection"],
)
def test_incomplete_evidence_refused(mutation):
    data = inputs()
    capture = data["captures"][0]
    if mutation == "truncated":
        capture["tree"]["truncated"] = True
    elif mutation == "missing_pair":
        del capture["documents"]["specs/demo/status.json"]
    elif mutation == "short_sha":
        capture["head"] = SHA[:10]
    elif mutation == "missing_alias":
        capture["tree"]["paths"].append(".config/spec-aliases.toml")
    elif mutation == "missing_target":
        capture["documents"]["specs/demo/requirements.md"] = capture["documents"]["specs/demo/requirements.md"].replace(
            f"Depends-on: `{A}`", "Depends-on: `OTHER-R001`"
        )
    elif mutation == "duplicate_repo":
        data["repositories"].append(REPO)
    elif mutation == "selection":
        data["selection"] = ["R_1:absent"]
    with pytest.raises((ContractError, SourceGap)):
        source_chart(**data)


def test_git_capture_pinned_commit_not_worktree(tmp_path):
    git_env = fixture_git_environment()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], env=git_env, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.test")
    git("remote", "add", "origin", "https://github.com/Knuckles-Team/pipelines.git")
    for path, body in inputs()["captures"][0]["documents"].items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    spec_id = json.loads(inputs()["captures"][0]["documents"]["specs/demo/status.json"])["spec_id"]
    (tmp_path / "specs/demo/spec.md").write_text(f"# {spec_id} — Demo\n")
    git("add", "specs/demo/requirements.md", "specs/demo/spec.md")
    git("commit", "-m", "Fixture")
    commit = git("rev-parse", "HEAD")
    (tmp_path / "specs/demo/requirements.md").write_text("corrupt worktree")
    captured = capture_git(tmp_path, commit, REPO)
    assert captured["head"] == commit
    assert source_chart(captures=[captured], repositories=[REPO], selection=["R_1:demo"])["scope"]["scoreRowCount"] == 2
    with pytest.raises(ContractError):
        capture_git(tmp_path, "HEAD", REPO)
    with pytest.raises(subprocess.CalledProcessError):
        capture_git(tmp_path, "0" * 40, REPO)


def test_family_view_keeps_complete_score_denominator_and_closure():
    data = inputs()
    capture = data["captures"][0]
    rid = "PIPE-OTHER-R001"
    capture["documents"]["specs/other/requirements.md"] = f"| `{rid}` | **Third**. Depends-on: `{B}`. | tests |\n"
    capture["documents"]["specs/other/status.json"] = json.dumps(
        {
            "schema_version": 2,
            "owner_repo": "pipelines",
            "delivery_state": "SPECIFIED",
            "requirement_ids": [rid],
            "spec_id": "PIPE-OTHER",
            "requirements": [{"id": rid, "delivery_state": "SPECIFIED", "landed_in": [], "verified_by": []}],
        }
    )
    capture["tree"]["paths"] = list(capture["documents"])
    data["selection"] = ["R_1:other"]
    result = source_chart(**data)
    assert result["scope"]["scoreRowCount"] == 3
    assert result["scope"]["selectedRowKeys"] == ["R_1:" + rid]
    assert result["scope"]["prerequisiteClosureRowKeys"] == sorted(["R_1:" + r for r in (A, B, rid)])
    assert result["rows"]["R_1:" + A]["priority"]["value"] == 4
    assert result["rows"]["R_1:" + A]["priority"]["inputs"]["openDependents"] == 2
    assert result["families"][0]["statusCounts"]["SPECIFIED"] == 1


def test_raw_alias_validator_matches_filesystem(tmp_path):
    from pipelines_hooks.specs.aliases import load_aliases, validate_alias_document
    import tomllib

    data = alias_input()
    for path, body in data["captures"][0]["documents"].items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    doc = tomllib.loads(data["captures"][0]["documents"][".config/spec-aliases.toml"])
    assert load_aliases(tmp_path) == validate_alias_document(
        doc, current_ids={A, B}, active_ids={A, B}, source_path=tmp_path / ".config/spec-aliases.toml"
    )


def test_prefix_alias_and_retired_target_semantics():
    data = alias_input('"OLD-" = "PIPE-DEMO-"')
    docs = data["captures"][0]["documents"]
    docs["specs/demo/requirements.md"] = docs["specs/demo/requirements.md"].replace("PIPE-DEMO-R009", "OLD-R001")
    result = source_chart(**data)
    resolution = result["rows"]["R_1:" + B]["dependencies"]["resolutions"][0]
    assert resolution["matchedAliasKey"] == "OLD-"
    assert resolution["aliasProvenance"]["fragment"] == "OLD-"


def test_cross_repository_alias_interpretation_conflict():
    data = alias_input()
    other = {"id": "R_2", "fullName": "Knuckles-Team/other", "url": "https://github.com/Knuckles-Team/other"}
    data["repositories"].append(other)
    rid = "OTHER-R001"
    docs = {
        "specs/other/requirements.md": f"| `{rid}` | **Other**. | tests |",
        "specs/other/status.json": json.dumps(
            {
                "schema_version": 2,
                "owner_repo": "other",
                "delivery_state": "SPECIFIED",
                "requirement_ids": [rid],
                "spec_id": "OTHER",
                "requirements": [{"id": rid, "delivery_state": "SPECIFIED", "landed_in": [], "verified_by": []}],
            }
        ),
        ".config/spec-aliases.toml": f'"PIPE-DEMO-R009" = "{rid}"',
    }
    data["captures"].append(
        {"repositoryId": "R_2", "head": SHA, "tree": {"truncated": False, "paths": list(docs)}, "documents": docs}
    )
    with pytest.raises(ContractError, match="ambiguous dependency"):
        source_chart(**data)


def test_no_inferred_interface_or_prose_edges():
    data = inputs()
    docs = data["captures"][0]["documents"]
    docs["specs/demo/requirements.md"] = docs["specs/demo/requirements.md"].replace(
        f"Depends-on: `{A}`.", "Depends-on: `scion-sdk` or another package."
    )
    result = source_chart(**data)
    row = result["rows"]["R_1:" + B]
    assert row["dependencies"]["keys"] == []
    assert row["sourceEvidence"]["dependencyContext"][0]["kind"] == "non_requirement_context"
    assert row["priority"]["value"] == 0


def with_outside_gap():
    data = inputs()
    capture = data["captures"][0]
    rid = "PIPE-OUTSIDE-R001"
    capture["documents"]["specs/outside/requirements.md"] = (
        f"| `{rid}` | **Outside**. Depends-on: `MISSING-R001`. | tests |"
    )
    capture["documents"]["specs/outside/status.json"] = json.dumps(
        {
            "schema_version": 2,
            "owner_repo": "pipelines",
            "delivery_state": "SPECIFIED",
            "requirement_ids": [rid],
            "spec_id": "PIPE-OUTSIDE",
            "requirements": [{"id": rid, "delivery_state": "SPECIFIED", "landed_in": [], "verified_by": []}],
        }
    )
    capture["tree"]["paths"] = list(capture["documents"])
    return data


def test_explicit_family_scope_preserves_excluded_gaps_not_auto_fallback():
    data = with_outside_gap()
    with pytest.raises(ContractError, match="MISSING-R001"):
        source_chart(**data)
    result = source_chart(**data, score_scope="selected-family-prerequisite-closure")
    assert result["scope"]["kind"] == "selected-family-prerequisite-closure"
    assert result["scope"]["capturedRowCount"] == 3
    assert result["scope"]["scoreRowCount"] == 2
    assert len(result["rows"]) == 2
    gaps = result["scope"]["excludedDependencyGaps"]
    assert gaps[0]["declaredId"] == "MISSING-R001"
    assert gaps[0]["provenance"]["commit"] == SHA
    assert gaps[0]["context"][0]["text"] == "Depends-on: `MISSING-R001`."


def test_selected_scope_cannot_hide_a_gap_in_transitive_closure():
    data = with_outside_gap()
    docs = data["captures"][0]["documents"]
    docs["specs/demo/requirements.md"] = docs["specs/demo/requirements.md"].replace(
        "**First**.", "**First**. Depends-on: `PIPE-OUTSIDE-R001`."
    )
    with pytest.raises(ContractError, match="MISSING-R001"):
        source_chart(**data, score_scope="selected-family-prerequisite-closure")


def test_scope_changes_denominator_explicitly_not_global_score_claim():
    data = with_outside_gap()
    docs = data["captures"][0]["documents"]
    docs["specs/outside/requirements.md"] = docs["specs/outside/requirements.md"].replace("MISSING-R001", A)
    full = source_chart(**data)
    scoped = source_chart(**data, score_scope="selected-family-prerequisite-closure")
    assert full["rows"]["R_1:" + A]["priority"]["value"] == 4
    assert scoped["rows"]["R_1:" + A]["priority"]["value"] == 2
    assert full["scope"]["kind"] != scoped["scope"]["kind"]
    assert full["scope"]["scoreRowCount"] == 3
    assert scoped["scope"]["scoreRowCount"] == 2


def test_malformed_alias_cannot_hide_outside_selection():
    data = alias_input('invalid = ["not", "a string"]')
    with pytest.raises(CannotRun):
        source_chart(**data, score_scope="selected-family-prerequisite-closure")


def test_foreign_rollup_members_are_evidence_only_not_silent_score_expansion():
    data = inputs()
    capture = data["captures"][0]
    docs = capture["documents"]
    parent, child = "PIPE-OTHER-R001", "PIPE-OTHER-R001.1"
    docs["specs/demo/requirements.md"] = docs["specs/demo/requirements.md"].replace(
        "**First**.", f"**First**. Depends-on: `{parent}`."
    )
    docs["specs/other/requirements.md"] = f"| `{parent}` | **Rollup**. | tests |\n| `{child}` | **Child**. | tests |\n"
    docs["specs/other/status.json"] = json.dumps(
        {
            "schema_version": 2,
            "owner_repo": "pipelines",
            "delivery_state": "SPECIFIED",
            "requirement_ids": [parent, child],
            "spec_id": "PIPE-OTHER",
            "requirements": [
                {"id": parent, "delivery_state": "SPECIFIED", "landed_in": [], "verified_by": [], "rollup_of": [child]},
                {"id": child, "delivery_state": "SPECIFIED", "landed_in": [], "verified_by": []},
            ],
        }
    )
    capture["tree"]["paths"] = list(docs)
    result = source_chart(**data, score_scope="selected-family-prerequisite-closure")
    assert result["scope"]["scoreRowCount"] == 3
    assert result["scope"]["evidenceOnlyRowCount"] == 1
    assert "R_1:" + child not in result["rows"]
    evidence = result["evidenceRows"]["R_1:" + child]
    assert evidence["scopeRole"] == "rollup_evidence_only_not_scored"
    assert evidence["provenance"]["commit"] == SHA
    assert "priority" not in evidence and "readiness" not in evidence
    assert result["rows"]["R_1:" + parent]["sourceEvidence"]["rollupOf"] == [evidence["key"]]


def test_known_uncaptured_repository_prerequisite_is_external_not_a_gap():
    from scripts.architecture_explorer import story_chart_sources as sources

    assert "MEDULLA" in sources.ORGANIZATION_SPEC_PREFIXES
    assert "MISSING" not in sources.ORGANIZATION_SPEC_PREFIXES
